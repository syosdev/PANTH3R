import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from music_player.strip import Strip


def main():
    app = Strip()
    app.run()


if __name__ == "__main__":
    main()
