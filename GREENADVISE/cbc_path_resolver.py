import os, sys

def get_cbc_executable_path():

    env_path = os.getenv("CBC_EXECUTABLE")
    if env_path and os.path.isfile(env_path):
        return env_path


    base = getattr(sys, "_MEIPASS", os.path.abspath(os.path.dirname(sys.argv[0])))
    bundled = os.path.join(base, "cbc", "cbc.exe")
    if os.path.isfile(bundled):
        return bundled


    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.join(here, "app_bin", "cbc.exe")
    if os.path.isfile(repo):
        return repo


    return "cbc"
