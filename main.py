import fire
import logging

from sync import sync

if __name__ == "__main__":
    # parser = argparse.ArgumentParser()
    # parser.add_argument("weread_cookie")
    # parser.add_argument("notion_token")
    # parser.add_argument("database_id")
    # options = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    fire.Fire({
      'sync': sync,
  })