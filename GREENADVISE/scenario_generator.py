

import os
import hashlib
import numpy as np

# ── Model weights directory ───────────────────────────────────────────────────
_HERE      = os.path.dirname(os.path.abspath(__file__))
_MODEL_DIR = os.path.join(_HERE, "models")
MODEL_PATH = os.path.join(_MODEL_DIR, "lstm_vae_weights.pt")

# ── Architecture version — increment whenever the model structure changes ─────
ARCH_VERSION = 7

# ── Hyper-parameters ──────────────────────────────────────────────────────────
N_HOURS      = 8760
N_DAYS       = 365
N_VARS_RAW   = 3        # physical outputs   : pv, wind, temp
N_VARS_IN    = 5        # encoder inputs     : raw + sin/cos day-of-year
HIDDEN_ENC   = 48       # per-direction hidden size (bidir → 96 combined)
HIDDEN_DIM   = 96       # MUST equal 2 × HIDDEN_ENC (bidirectional encoder output)
N_LAYERS     = 1        # single LSTM layer — fast, still captures seasonality
DROPOUT      = 0.0      # no dropout with 1 layer
LATENT_DIM   = 24       # enough expressiveness for 10 training years
LAMBDA_KL    = 0.3      # low KL weight → encoder encodes real inter-year variation
N_CYCLES_KL  = 2        # 2 KL annealing cycles
N_AUGMENT    = 8        # augmentation rounds per real year
N_MC_SAMPLES = 1000     # Monte Carlo draws — wider pool for diverse tail scenarios
N_REDUCED    = 10       # representative scenarios after Heitsch-Romisch
N_SEASONS    = 4        # DJF / MAM / JJA / SON seasonal diurnal profiles
BATCH_SIZE   = 16
N_EPOCHS     = 30       # 30 epochs — needed for stable KL + latent diversity
LR           = 3e-4
FREE_BITS    = 0.5      # nats/dim KL floor — prevents posterior collapse
MC_TEMP      = 1.8      # latent sampling temperature — spreads MC scenarios wider

VARIABLES = ["pv", "wind", "temp"]

# ── Day-of-year positional encoding  (365 × 2, precomputed) ──────────────────
_DOY     = np.arange(N_DAYS, dtype=np.float32)
_POS_ENC = np.stack([
    np.sin(2.0 * np.pi * _DOY / N_DAYS),
    np.cos(2.0 * np.pi * _DOY / N_DAYS),
], axis=1).astype(np.float32)   # (365, 2)

# ── Seasonal assignment per day-of-year (meteorological seasons) ──────────────
# Season 0 DJF (Winter) : days   0– 59  and  335–364
# Season 1 MAM (Spring) : days  60–151
# Season 2 JJA (Summer) : days 152–242
# Season 3 SON (Autumn) : days 243–334
def _day_to_season(d: int) -> int:
    if d < 60 or d >= 335:
        return 0   # Winter
    elif d < 152:
        return 1   # Spring
    elif d < 243:
        return 2   # Summer
    else:
        return 3   # Autumn

_SEASON_OF_DAY = np.array([_day_to_season(d) for d in range(N_DAYS)], dtype=int)


def _add_positional_encoding(daily_norm: np.ndarray) -> np.ndarray:
    """(N, 365, 3) → (N, 365, 5)  by appending sin/cos columns."""
    N   = daily_norm.shape[0]
    pos = np.tile(_POS_ENC[np.newaxis], (N, 1, 1))
    return np.concatenate([daily_norm, pos], axis=2).astype(np.float32)


# ── Cyclical KL annealing schedule ───────────────────────────────────────────
def _cyclic_kl_weight(epoch: int) -> float:
    """
    Cyclical KL annealing (Fu et al., 2019).
    Linearly ramps from 0 → LAMBDA_KL in the first half of each cycle,
    then holds at LAMBDA_KL for the second half.  Resets each cycle.
    """
    cycle_len = N_EPOCHS / N_CYCLES_KL          # epochs per cycle
    pos       = (epoch % cycle_len) / cycle_len  # position in [0, 1)
    return min(1.0, pos * 2.0) * LAMBDA_KL


# ─────────────────────────────────────────────────────────────────────────────
# torch import
# ─────────────────────────────────────────────────────────────────────────────

def _require_torch():
    try:
        import torch
        torch.set_num_threads(1)   # prevent GIL conflicts in Qt threads (Windows)
        return torch
    except (ImportError, OSError) as e:
        raise ImportError(
            "PyTorch could not be loaded.\n"
            f"Reason: {e}\n\n"
            "If you see a DLL error on Windows, install the Visual C++ Redistributable:\n"
            "  https://aka.ms/vs/17/release/vc_redist.x64.exe\n\n"
            "Then install PyTorch:\n"
            "  pip install torch"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 1.  LSTM-VAE model  (advanced architecture)
# ─────────────────────────────────────────────────────────────────────────────

def _build_model():
    """
    Build the advanced LSTM-VAE.

    Encoder
    -------
    Bidirectional 2-layer LSTM (hidden = HIDDEN_ENC=64 per direction)
    + temporal soft-attention pooling over all 365 day-states
    → μ, log σ²  in ℝ^LATENT_DIM

    The bidirectional LSTM reads the year forward and backward,
    capturing both "spring → summer" and "autumn → summer" dependencies.
    Soft-attention lets the model weight each day by its informativeness.

    Decoder
    -------
    2-layer LSTM (hidden = HIDDEN_DIM=128), seeded from latent z.
    Receives sin/cos day-of-year as step input for explicit seasonal guidance.
    → (batch, 365, N_VARS_RAW=3)
    """
    torch   = _require_torch()
    nn      = torch.nn
    F       = torch.nn.functional
    _dropout = DROPOUT if N_LAYERS > 1 else 0.0

    class TemporalAttention(nn.Module):
        """Soft attention: weighted sum of LSTM outputs over the time axis."""
        def __init__(self, hidden_size: int):
            super().__init__()
            self.score = nn.Linear(hidden_size, 1, bias=False)

        def forward(self, x):              # x : (B, T, H)
            w = torch.softmax(self.score(x), dim=1)   # (B, T, 1)
            return (x * w).sum(dim=1)     # (B, H)

    class Encoder(nn.Module):
        def __init__(self):
            super().__init__()
            # Bidirectional: output dim = 2 × HIDDEN_ENC = HIDDEN_DIM
            self.lstm    = nn.LSTM(
                N_VARS_IN, HIDDEN_ENC, N_LAYERS,
                batch_first=True, bidirectional=True, dropout=_dropout,
            )
            self.attn       = TemporalAttention(HIDDEN_DIM)
            self.norm       = nn.LayerNorm(HIDDEN_DIM)
            self.fc_mu      = nn.Linear(HIDDEN_DIM, LATENT_DIM)
            self.fc_log_var = nn.Linear(HIDDEN_DIM, LATENT_DIM)

        def forward(self, x):              # x : (B, 365, 5)
            out, _ = self.lstm(x)          # (B, 365, 128)
            h      = self.attn(out)        # (B, 128) — attention-pooled
            h      = self.norm(h)
            return self.fc_mu(h), self.fc_log_var(h)

    class Decoder(nn.Module):
        def __init__(self):
            super().__init__()
            # Seed all layers' hidden + cell states from z
            self.fc_h = nn.Linear(LATENT_DIM, HIDDEN_DIM * N_LAYERS)
            self.fc_c = nn.Linear(LATENT_DIM, HIDDEN_DIM * N_LAYERS)
            # input_size=2: sin/cos positional encoding provides seasonal context
            self.lstm = nn.LSTM(
                2, HIDDEN_DIM, N_LAYERS,
                batch_first=True, dropout=_dropout,
            )
            self.fc_out = nn.Linear(HIDDEN_DIM, N_VARS_RAW)

        def forward(self, z, pos_enc_t):   # z : (B, LATENT); pos_enc_t : (B, 365, 2)
            B  = z.size(0)
            h0 = self.fc_h(z).view(N_LAYERS, B, HIDDEN_DIM).contiguous()
            c0 = self.fc_c(z).view(N_LAYERS, B, HIDDEN_DIM).contiguous()
            out, _ = self.lstm(pos_enc_t, (h0, c0))   # (B, 365, 128)
            return self.fc_out(out)                    # (B, 365, 3)

    class LSTMVAE(nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = Encoder()
            self.decoder = Decoder()
            # Device-aware positional encoding buffer
            self.register_buffer(
                "pos_enc", torch.tensor(_POS_ENC, dtype=torch.float32)
            )   # (365, 2)

        def reparameterize(self, mu, log_var):
            std = torch.exp(0.5 * log_var)
            return mu + torch.randn_like(std) * std

        def forward(self, x):              # x : (B, 365, 5)
            mu, log_var = self.encoder(x)
            z     = self.reparameterize(mu, log_var)
            pos_t = self.pos_enc.unsqueeze(0).expand(x.size(0), -1, -1)
            x_hat = self.decoder(z, pos_t)             # (B, 365, 3)
            return x_hat, mu, log_var, z

        def compute_loss(self, x_raw, x_hat, mu, log_var, kl_weight: float):
            """
            x_raw : (B, 365, 3)  physical channels
            x_hat : (B, 365, 3)
            Free-bits KL: clamp each latent dimension to FREE_BITS minimum
            so the posterior never fully collapses to the prior.
            """
            recon = F.mse_loss(x_hat, x_raw, reduction="mean")
            # Per-dimension KL then free-bits floor
            kl_per_dim = -0.5 * (1 + log_var - mu.pow(2) - log_var.exp())  # (B, D)
            kl = torch.clamp(kl_per_dim, min=FREE_BITS).mean()
            return recon + kl_weight * kl, recon, kl

    return LSTMVAE


# ─────────────────────────────────────────────────────────────────────────────
# 2.  Daily aggregation and hourly reconstruction
# ─────────────────────────────────────────────────────────────────────────────

def _hourly_to_daily(historical_years: list) -> tuple:
    """
    Aggregate 8760-h arrays to 365-day arrays.

    PV / Wind → daily SUM  (kWh per day)
    Temp       → daily MEAN (°C)

    Returns
    -------
    daily_data  : np.ndarray  (N, 365, 3)      — min-max normalised to [0, 1]
    diurnal_tpl : np.ndarray  (N_SEASONS, 24, 3) — per-season mean diurnal profile
    norm_params : dict  {variable: (min, max)}
    """
    N = len(historical_years)
    if N == 0:
        raise ValueError(
            "No historical weather data was fetched from Renewables.ninja.\n"
            "Please check your API key, internet connection, and try again."
        )
    daily_data    = np.zeros((N, N_DAYS, N_VARS_RAW), dtype=np.float32)
    # Accumulate seasonal diurnal profiles (4 seasons × 24 h × 3 vars)
    diurnal_acc   = np.zeros((N_SEASONS, 24, N_VARS_RAW), dtype=np.float64)
    # Count how many (year × day) samples contribute to each season
    season_counts = np.bincount(_SEASON_OF_DAY, minlength=N_SEASONS).astype(np.float64)

    for i, yr in enumerate(historical_years):
        for v_idx, v_name in enumerate(VARIABLES):
            arr = np.asarray(yr.get(v_name, np.zeros(N_HOURS)), dtype=np.float32)
            arr = arr[:N_HOURS]
            if len(arr) < N_HOURS:
                arr = np.pad(arr, (0, N_HOURS - len(arr)))
            h2d = arr.reshape(N_DAYS, 24)   # (365, 24)
            daily_data[i, :, v_idx] = h2d.mean(axis=1) if v_name == "temp" else h2d.sum(axis=1)
            # Accumulate into the appropriate seasonal bin
            for s in range(N_SEASONS):
                mask = (_SEASON_OF_DAY == s)
                diurnal_acc[s, :, v_idx] += h2d[mask].sum(axis=0)

    # Normalise: divide by (N years × days in season)
    diurnal_tpl = diurnal_acc.copy()
    for s in range(N_SEASONS):
        if season_counts[s] > 0:
            diurnal_tpl[s] /= (N * season_counts[s])

    norm_params = {}
    for v_idx, v_name in enumerate(VARIABLES):
        v_min = float(daily_data[:, :, v_idx].min())
        v_max = float(daily_data[:, :, v_idx].max())
        daily_data[:, :, v_idx] = (
            (daily_data[:, :, v_idx] - v_min) / (v_max - v_min + 1e-8)
        )
        norm_params[v_name] = (v_min, v_max)

    return daily_data, diurnal_tpl, norm_params


def _inverse_normalise_daily(daily_norm: np.ndarray, norm_params: dict) -> np.ndarray:
    """Un-normalise (N, 365, 3) back to physical units."""
    result = daily_norm.copy()
    for v_idx, v_name in enumerate(VARIABLES):
        v_min, v_max = norm_params[v_name]
        result[:, :, v_idx] = daily_norm[:, :, v_idx] * (v_max - v_min) + v_min
    return result


def _reconstruct_hourly(daily_physical: np.ndarray, diurnal_tpl: np.ndarray) -> list:
    """
    Convert (N, 365, 3) daily physical values back to 8760-h arrays.

    Uses per-season diurnal profiles (N_SEASONS=4) so that winter days get a
    different sunrise/sunset shape than summer days.

    PV / Wind : scale seasonal diurnal profile → daily total matches target
    Temp       : shift seasonal diurnal profile → daily mean matches target

    Returns list of N dicts  {'pv': (8760,), 'wind': (8760,), 'temp': (8760,)}
    """
    N = daily_physical.shape[0]
    scenarios = []

    for i in range(N):
        hourly = np.zeros((N_DAYS, 24, N_VARS_RAW), dtype=np.float32)
        for d in range(N_DAYS):
            season = _SEASON_OF_DAY[d]          # which of the 4 seasonal profiles to use
            for v_idx, v_name in enumerate(VARIABLES):
                profile = diurnal_tpl[season, :, v_idx]
                target  = daily_physical[i, d, v_idx]
                if v_name == "temp":
                    hourly[d, :, v_idx] = profile + (target - profile.mean())
                else:
                    s = profile.sum()
                    hourly[d, :, v_idx] = (
                        np.maximum(profile * (target / s), 0.0) if s > 1e-8 else 0.0
                    )
        flat = hourly.reshape(N_HOURS, N_VARS_RAW)
        scenarios.append({v: flat[:, i].copy() for i, v in enumerate(VARIABLES)})

    return scenarios


# ─────────────────────────────────────────────────────────────────────────────
# 3.  Data augmentation
# ─────────────────────────────────────────────────────────────────────────────

def _augment_training_data(daily_norm: np.ndarray, n_rounds: int = N_AUGMENT) -> np.ndarray:
    """
    Augment normalised (N, 365, 3) daily data to ~(N × (2n+1) + mix, 365, 3).

    Strategies
    ----------
    1. Gaussian noise   : additive noise σ=0.025 in normalised space
    2. Magnitude jitter : per-year, per-variable scale in [0.88, 1.12]
    3. Season mixing    : new years spliced from seasonal blocks of different
                          real years — preserves within-season correlations

    Returns concatenated array including the originals.
    """
    rng = np.random.default_rng(seed=0)   # fixed seed for reproducibility
    N, D, V = daily_norm.shape
    parts   = [daily_norm]

    # 1. Noise augmentation
    for _ in range(n_rounds):
        noise = rng.normal(0.0, 0.025, daily_norm.shape).astype(np.float32)
        parts.append(np.clip(daily_norm + noise, 0.0, 1.0))

    # 2. Magnitude scale augmentation
    for _ in range(n_rounds):
        scale = rng.uniform(0.88, 1.12, (N, 1, V)).astype(np.float32)
        parts.append(np.clip(daily_norm * scale, 0.0, 1.0))

    # 3. Season mixing: splice DJF/MAM/JJA/SON blocks from different real years
    season_bounds = [(0, 90), (90, 181), (181, 273), (273, 365)]
    n_mix = max(N * 3, 60)
    for _ in range(n_mix):
        mixed = np.zeros((1, D, V), dtype=np.float32)
        for d0, d1 in season_bounds:
            src = rng.integers(0, N)
            mixed[0, d0:d1, :] = daily_norm[src, d0:d1, :]
        parts.append(mixed)

    augmented = np.concatenate(parts, axis=0)
    return augmented


# ─────────────────────────────────────────────────────────────────────────────
# 4.  Training  (augmentation + cyclical KL annealing)
# ─────────────────────────────────────────────────────────────────────────────

def train_lstm_vae(
    historical_years: list,
    save_path: str = MODEL_PATH,
    progress_callback=None,
):
    """
    Train the advanced LSTM-VAE.

    Architecture: bidirectional LSTM encoder + temporal attention
                  2-layer LSTM decoder with sin/cos positional input
    Training:     data augmentation + cyclical KL annealing

    Returns
    -------
    model       : trained LSTMVAE (eval mode)
    norm_params : dict of normalisation parameters
    diurnal_tpl : np.ndarray (365, 24, 3) — from real data only
    """
    torch         = _require_torch()
    TensorDataset = torch.utils.data.TensorDataset
    DataLoader    = torch.utils.data.DataLoader
    LSTMVAE       = _build_model()

    def _log(msg):
        if progress_callback:
            progress_callback(msg)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    _log(f"Training advanced LSTM-VAE on {len(historical_years)} historical years "
         f"({device})  —  arch v{ARCH_VERSION}, {N_EPOCHS} epochs...")

    # ── Prepare real data and diurnal template ────────────────────────────────
    daily_data, diurnal_tpl, norm_params = _hourly_to_daily(historical_years)

    # ── Augment training data ─────────────────────────────────────────────────
    _log(f"Augmenting {len(historical_years)} real years ...")
    augmented    = _augment_training_data(daily_data, n_rounds=N_AUGMENT)
    data_enc     = _add_positional_encoding(augmented)               # (N_aug, 365, 5)
    _log(f"Training set: {len(augmented)} samples "
         f"({len(historical_years)} real + {len(augmented)-len(historical_years)} synthetic)")

    data_tensor  = torch.tensor(data_enc)
    dataset      = TensorDataset(data_tensor)
    dataloader   = DataLoader(dataset, batch_size=BATCH_SIZE,
                              shuffle=True, num_workers=0)

    # ── Model + optimiser ────────────────────────────────────────────────────
    model     = LSTMVAE().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=1e-5)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=N_EPOCHS)

    # ── Training loop ────────────────────────────────────────────────────────
    model.train()
    for epoch in range(N_EPOCHS):
        kl_weight  = _cyclic_kl_weight(epoch)
        epoch_loss = 0.0
        last_recon = last_kl = 0.0

        for (batch,) in dataloader:
            batch = batch.to(device)
            x_raw = batch[:, :, :N_VARS_RAW]          # physical channels only

            optimizer.zero_grad()
            x_hat, mu, log_var, _ = model(batch)
            loss, recon, kl = model.compute_loss(x_raw, x_hat, mu, log_var, kl_weight)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

            epoch_loss += loss.item()
            last_recon, last_kl = recon.item(), kl.item()

        scheduler.step()

        # Log every epoch (N_EPOCHS is small)
        avg = epoch_loss / max(len(dataloader), 1)
        _log(f"  Epoch {epoch+1:>3}/{N_EPOCHS} | "
             f"loss={avg:.5f}  recon={last_recon:.5f}  "
             f"kl={last_kl:.5f}  kl_w={kl_weight:.2f}")

    model.eval()

    # ── Save checkpoint ───────────────────────────────────────────────────────
    years_str = str(sorted(yr.get("year", i) for i, yr in enumerate(historical_years)))
    data_hash = hashlib.md5(years_str.encode()).hexdigest()[:12]

    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    torch.save({
        "model_state":   model.state_dict(),
        "norm_params":   norm_params,
        "diurnal_tpl":   diurnal_tpl,
        "data_hash":     data_hash,
        "arch_version":  ARCH_VERSION,
    }, save_path)
    _log(f"Model saved to {save_path}")

    return model, norm_params, diurnal_tpl


# ─────────────────────────────────────────────────────────────────────────────
# 5.  Load saved model
# ─────────────────────────────────────────────────────────────────────────────

def load_lstm_vae(load_path: str = MODEL_PATH):
    """
    Load a previously trained LSTM-VAE from disk.

    Returns
    -------
    model       : LSTMVAE in eval mode
    norm_params : dict
    diurnal_tpl : np.ndarray (365, 24, 3)
    """
    torch   = _require_torch()
    LSTMVAE = _build_model()

    ckpt        = torch.load(load_path, map_location="cpu", weights_only=False)
    model       = LSTMVAE()
    model.load_state_dict(ckpt["model_state"])
    model.eval()
    diurnal_tpl = ckpt.get("diurnal_tpl", np.zeros((N_SEASONS, 24, N_VARS_RAW)))
    return model, ckpt["norm_params"], diurnal_tpl


# ─────────────────────────────────────────────────────────────────────────────
# 6.  Monte Carlo sampling  (1 000 scenarios)
# ─────────────────────────────────────────────────────────────────────────────

def monte_carlo_sample(
    model,
    norm_params: dict,
    diurnal_tpl: np.ndarray,
    n_samples: int = N_MC_SAMPLES,
    progress_callback=None,
) -> list:
    """
    Draw n_samples synthetic scenarios from the LSTM-VAE latent space.
    Reconstructs full 8760-h profiles via historical diurnal templates.

    Returns list of dicts  {'pv': (8760,), 'wind': (8760,), 'temp': (8760,)}
    """
    torch = _require_torch()

    def _log(msg):
        if progress_callback:
            progress_callback(msg)

    device   = next(model.parameters()).device
    batch_sz = 50
    all_daily = []

    _log(f"Sampling {n_samples} synthetic scenarios from latent space...")

    model.eval()
    with torch.no_grad():
        generated = 0
        while generated < n_samples:
            current = min(batch_sz, n_samples - generated)
            # MC_TEMP > 1 widens the latent sampling distribution,
            # producing more diverse extreme scenarios
            z     = torch.randn(current, LATENT_DIM, device=device) * MC_TEMP
            pos_t = model.pos_enc.unsqueeze(0).expand(current, -1, -1)
            x_hat = model.decoder(z, pos_t)
            x_hat = torch.clamp(x_hat, 0.0, 1.0).cpu().numpy()
            all_daily.append(x_hat)
            generated += current

    all_daily      = np.concatenate(all_daily, axis=0)[:n_samples]   # (N, 365, 3)
    daily_physical = _inverse_normalise_daily(all_daily, norm_params)
    scenarios      = _reconstruct_hourly(daily_physical, diurnal_tpl)

    _log(f"Generated {len(scenarios)} synthetic scenarios (hourly, 8760 h).")
    return scenarios


# ─────────────────────────────────────────────────────────────────────────────
# 6b.  Historical bootstrap sampling  (diversity from real data)
# ─────────────────────────────────────────────────────────────────────────────

def historical_bootstrap_sample(
    daily_norm: np.ndarray,
    norm_params: dict,
    diurnal_tpl: np.ndarray,
    n_samples: int = N_MC_SAMPLES,
    progress_callback=None,
) -> list:
    """
    Generate diverse scenarios by bootstrapping from real historical years.

    Each draw is one of three strategies chosen randomly:
      - Direct copy of a historical year (with magnitude scaling)
      - Season-mixed year: each of 4 seasonal blocks from a different year
      - Cross-variable mix: PV from one year, wind/temp from another

    Magnitude scaling draws each variable independently from N(1, 0.07),
    clipped to [0.78, 1.22], so a good PV year can be 22% above / below
    average — matching realistic inter-year variability for Central Europe.

    This guarantees physically realistic spread that is independent of the
    LSTM-VAE posterior (which can collapse in small 20-year datasets).
    """
    def _log(msg):
        if progress_callback:
            progress_callback(msg)

    rng = np.random.default_rng()
    N_years = daily_norm.shape[0]
    if N_years == 0:
        raise ValueError(
            "Bootstrap sampling requires at least one historical year, but none were loaded.\n"
            "Check your Renewables.ninja API key and internet connection."
        )
    season_bounds = [(0, 90), (90, 181), (181, 273), (273, 365)]

    _log(f"Sampling {n_samples} scenarios via historical bootstrap ({N_years} base years)...")
    samples = np.zeros((n_samples, N_DAYS, N_VARS_RAW), dtype=np.float32)

    for i in range(n_samples):
        strategy = rng.random()

        if strategy < 0.33:
            # Direct historical year
            base = rng.integers(0, N_years)
            s = daily_norm[base].copy()
        elif strategy < 0.67:
            # Season mixing: each seasonal block from a (possibly different) year
            s = daily_norm[rng.integers(0, N_years)].copy()
            for d0, d1 in season_bounds:
                s[d0:d1, :] = daily_norm[rng.integers(0, N_years), d0:d1, :]
        else:
            # Cross-variable mix: PV from one year, wind+temp from another
            s = daily_norm[rng.integers(0, N_years)].copy()
            pv_src = rng.integers(0, N_years)
            s[:, 0] = daily_norm[pv_src, :, 0]   # PV column

        # Magnitude scaling per variable (independent)
        scale = rng.normal(1.0, 0.07, (1, N_VARS_RAW)).astype(np.float32)
        scale = np.clip(scale, 0.78, 1.22)
        samples[i] = np.clip(s * scale, 0.0, 1.0)

    _log(f"Generated {n_samples} bootstrap scenarios (hourly, 8760 h).")
    daily_physical = _inverse_normalise_daily(samples, norm_params)
    return _reconstruct_hourly(daily_physical, diurnal_tpl)


# ─────────────────────────────────────────────────────────────────────────────
# 7.  Scenario reduction — Heitsch–Römisch backward algorithm
# ─────────────────────────────────────────────────────────────────────────────

def _build_feature_matrix(scenarios: list) -> np.ndarray:
    """
    Monthly mean + std per variable — shape (N, 72).
    Fully vectorised: no Python loops over scenarios.
    """
    month_idx = np.clip(np.arange(N_HOURS) // 730, 0, 11)
    data      = {v: np.stack([np.asarray(s[v], dtype=np.float32)
                               for s in scenarios]) for v in VARIABLES}
    cols = []
    for v in VARIABLES:
        mat = data[v]
        for m in range(12):
            sub = mat[:, month_idx == m]
            cols.append(sub.mean(axis=1))
            cols.append(sub.std(axis=1))
    return np.stack(cols, axis=1).astype(np.float64)


def _heitsch_romisch_reduce(
    scenarios: list,
    feature_matrix: np.ndarray,
    n_reduced: int,
) -> tuple:
    """
    Backward scenario reduction (Heitsch & Römisch, 2003).  O(N²) total.

    Iteratively removes the scenario i* with minimum Kantorovich cost:
        cost(i) = p_i × min_{j active, j≠i} d(x_i, x_j)
    and redistributes p_i to its nearest active neighbour.
    """
    N     = len(scenarios)
    probs = np.ones(N) / N
    active = np.ones(N, dtype=bool)

    # ── Precompute normalised pairwise distance matrix (N × N) ───────────────
    feat_std  = feature_matrix.std(axis=0) + 1e-8
    feat_norm = (feature_matrix / feat_std).astype(np.float64)

    sq_norms = (feat_norm ** 2).sum(axis=1)
    dot_mat  = feat_norm @ feat_norm.T
    sq_dist  = sq_norms[:, None] + sq_norms[None, :] - 2 * dot_mat
    np.maximum(sq_dist, 0.0, out=sq_dist)
    dist_mat = np.sqrt(sq_dist)
    np.fill_diagonal(dist_mat, np.inf)

    # ── Backward elimination — O(N) per step using masked working matrix ──────
    working   = dist_mat.copy()
    n_current = N

    while n_current > n_reduced:
        nn_dist_all = working.min(axis=1)          # (N,) — inf for removed

        with np.errstate(invalid="ignore"):
            kantorovich = probs * nn_dist_all      # 0×inf=nan for removed; masked below
        kantorovich[~active] = np.inf

        remove_global = int(kantorovich.argmin())
        absorb_global = int(working[remove_global].argmin())

        probs[absorb_global] += probs[remove_global]
        probs[remove_global]  = 0.0
        active[remove_global] = False

        working[remove_global, :] = np.inf
        working[:, remove_global] = np.inf
        n_current -= 1

    final_idx   = np.where(active)[0]
    reduced     = [scenarios[i] for i in final_idx]
    final_probs = (probs[final_idx] / probs[final_idx].sum()).tolist()
    return reduced, final_probs


# ─────────────────────────────────────────────────────────────────────────────
# 8.  Tail scenario injection
# ─────────────────────────────────────────────────────────────────────────────

def _inject_tail_scenarios(
    reduced: list,
    probs: list,
    mc_scenarios: list,
    n_reduced: int,
) -> tuple:
    """
    Force best-case (max renewable) and worst-case (min renewable) scenarios
    into the reduced set.  Replaces the most-median (redundant) scenario if
    the tail is not already covered within 5 % of the value range.
    """
    renewable  = np.array([s["pv"].sum() + s["wind"].sum() for s in mc_scenarios])
    candidates = [int(renewable.argmin()), int(renewable.argmax())]

    reduced    = list(reduced)
    probs      = list(probs)
    reduced_rv = [s["pv"].sum() + s["wind"].sum() for s in reduced]
    rv_range   = float(renewable.max() - renewable.min()) + 1e-8

    for cand_idx in candidates:
        cand_val  = float(renewable[cand_idx])
        if any(abs(rv - cand_val) / rv_range < 0.05 for rv in reduced_rv):
            continue   # already well represented

        median_val    = float(np.median(reduced_rv))
        replace_local = int(np.argmin([abs(rv - median_val) for rv in reduced_rv]))
        freed_prob    = probs[replace_local]

        reduced.pop(replace_local)
        probs.pop(replace_local)
        reduced_rv.pop(replace_local)

        tail_prob = max(freed_prob * 0.5, 1.0 / (n_reduced * 4))
        reduced.append(mc_scenarios[cand_idx])
        probs.append(tail_prob)
        reduced_rv.append(cand_val)

    total = sum(probs)
    return reduced, [p / total for p in probs]


def reduce_scenarios(
    scenarios: list,
    n_reduced: int = N_REDUCED,
    progress_callback=None,
) -> tuple:
    """
    Heitsch-Römisch backward reduction + tail scenario injection.

    Returns
    -------
    reduced_scenarios : list of n_reduced dicts
    probabilities     : list of n_reduced floats  (sum = 1.0)
    """
    def _log(msg):
        if progress_callback:
            progress_callback(msg)

    n_reduced = min(n_reduced, len(scenarios))
    _log(f"Reducing {len(scenarios)} to {n_reduced} scenarios "
         f"(Heitsch-Romisch backward reduction)...")

    feat          = _build_feature_matrix(scenarios)
    reduced, probs = _heitsch_romisch_reduce(scenarios, feat, n_reduced)

    _log("Injecting best-case / worst-case tail scenarios...")
    reduced, probs = _inject_tail_scenarios(reduced, probs, scenarios, n_reduced)

    _log(f"Reduction complete.  "
         f"Prob range: [{min(probs):.4f}, {max(probs):.4f}]  "
         f"n={len(reduced)}")
    return reduced, probs


# ─────────────────────────────────────────────────────────────────────────────
# 9.  Main entry point  (with smart caching)
# ─────────────────────────────────────────────────────────────────────────────

def generate_scenarios(
    historical_years: list,
    n_reduced: int = N_REDUCED,
    retrain: bool = False,
    progress_callback=None,
    lat: float = None,
    lon: float = None,
) -> tuple:
    """
    Full pipeline:
      historical data
        → augmentation (×~19)
        → LSTM-VAE training (bidir + attention, cyclical KL)
        → Monte Carlo  (1 000 samples)
        → hourly reconstruction via diurnal profiles
        → Heitsch-Römisch reduction + tail injection

    Smart caching: retrains only when location, historical years, or
    architecture version have changed.

    Parameters
    ----------
    lat, lon : float, optional
        Location coordinates — included in the cache key so switching
        locations always triggers a retrain.

    Returns
    -------
    scenarios     : list of n_reduced dicts  {'pv', 'wind', 'temp'} (8760,)
    probabilities : list of n_reduced floats  (sum = 1.0)
    """
    def _log(msg):
        if progress_callback:
            progress_callback(msg)

    # ── Try LSTM-VAE training/loading (optional — only for norm_params cache) ─
    # The bootstrap sampler needs norm_params + diurnal_tpl.  We try to get
    # them from the LSTM-VAE checkpoint; if PyTorch is unavailable (e.g. a
    # DLL error on Windows) we fall back to computing them directly from the
    # historical data using pure NumPy — bootstrap sampling works identically.
    norm_params = None
    diurnal_tpl = None
    try:
        torch = _require_torch()
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        years_str    = str(sorted(yr.get("year", i) for i, yr in enumerate(historical_years)))
        loc_str      = (f"{round(float(lat), 4)}_{round(float(lon), 4)}"
                        if (lat is not None and lon is not None) else "unknown")
        current_hash = hashlib.md5(
            f"{loc_str}|{years_str}|v{ARCH_VERSION}".encode()
        ).hexdigest()[:12]

        needs_train = retrain
        if not needs_train:
            if not os.path.exists(MODEL_PATH):
                needs_train = True
                _log("No saved model found — training LSTM-VAE from scratch...")
            else:
                try:
                    ckpt       = torch.load(MODEL_PATH, map_location="cpu", weights_only=False)
                    saved_hash = ckpt.get("data_hash", "")
                    saved_arch = ckpt.get("arch_version", 0)
                    if saved_hash != current_hash or saved_arch != ARCH_VERSION:
                        needs_train = True
                        _log("Location / years / architecture changed — retraining LSTM-VAE...")
                    else:
                        _log("Loading cached LSTM-VAE model (same location, years, architecture)...")
                except Exception:
                    needs_train = True
                    _log("Cached model unreadable — retraining LSTM-VAE...")

        if needs_train:
            _, norm_params, diurnal_tpl = train_lstm_vae(
                historical_years, save_path=MODEL_PATH,
                progress_callback=progress_callback,
            )
        else:
            _, norm_params, diurnal_tpl = load_lstm_vae(MODEL_PATH)

    except (ImportError, OSError):
        # PyTorch DLL missing / not installed — bootstrap still works fine.
        _log("[PyTorch unavailable — running numpy-only bootstrap (no LSTM-VAE model cache)]")

    # ── Bootstrap: 1 000 scenarios from real historical years ────────────────
    # Uses historical data directly rather than VAE Monte Carlo because the
    # VAE posterior collapses in small datasets (20 years), making all MC
    # samples near-identical. Bootstrap from real years preserves genuine
    # inter-year weather variability (±10-15% PV, ±20% wind year-on-year).
    daily_data, _diurnal, _norm = _hourly_to_daily(historical_years)
    if norm_params is None:
        norm_params = _norm
    if diurnal_tpl is None:
        diurnal_tpl = _diurnal

    synthetic = historical_bootstrap_sample(
        daily_data, norm_params, diurnal_tpl,
        n_samples=N_MC_SAMPLES,
        progress_callback=progress_callback,
    )

    # ── Heitsch-Römisch reduction + tail injection ────────────────────────────
    reduced, probs = reduce_scenarios(
        synthetic, n_reduced=n_reduced,
        progress_callback=progress_callback,
    )

    _log(f"Scenario generation complete: {len(reduced)} scenarios, "
         f"{len(historical_years)} training years.")
    return reduced, probs


# ─────────────────────────────────────────────────────────────────────────────
# 10. Validation helpers
# ─────────────────────────────────────────────────────────────────────────────

def validate_scenarios(scenarios: list) -> dict:
    """Quality metrics for generated scenarios."""
    pv_annual   = [s["pv"].sum()    for s in scenarios]
    wind_annual = [s["wind"].sum()  for s in scenarios]
    temp_means  = [s["temp"].mean() for s in scenarios]

    def _corr(a, b):
        return float(np.corrcoef(a, b)[0, 1]) if len(a) > 2 else 0.0

    return {
        "n_scenarios":    len(scenarios),
        "pv_mean_kwh":    float(np.mean(pv_annual)),
        "wind_mean_kwh":  float(np.mean(wind_annual)),
        "pv_std_kwh":     float(np.std(pv_annual)),
        "wind_std_kwh":   float(np.std(wind_annual)),
        "pv_cv":          float(np.std(pv_annual) / (np.mean(pv_annual) + 1e-8)),
        "wind_cv":        float(np.std(wind_annual) / (np.mean(wind_annual) + 1e-8)),
        "pv_temp_corr":   _corr(pv_annual, temp_means),
        "wind_temp_corr": _corr(wind_annual, temp_means),
    }
