
import os
import pytest

if __name__ == "__main__":
    os.chdir(os.path.dirname(__file__))
    pytest.main(["-v", "tests"])
