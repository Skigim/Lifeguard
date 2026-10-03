from lifeguard.bot import run
from lifeguard.config import load_settings_from_dotenv

if __name__ == "__main__":
    run(load_settings_from_dotenv())
