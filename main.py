import fire
import logging

from sync import sync

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    fire.Fire({
      'sync': sync,
  })