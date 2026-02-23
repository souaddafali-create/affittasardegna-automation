import os
import requests

API_URL = os.environ["CASEVACANZA_API_URL"]
API_KEY = os.environ["CASEVACANZA_API_KEY"]


def load_listings(path: str = "listings.json") -> list[dict]:
    import json
    with open(path) as f:
        return json.load(f)


def upload_listing(session: requests.Session, listing: dict) -> None:
    response = session.post(f"{API_URL}/listings", json=listing)
    response.raise_for_status()
    print(f"Uploaded: {listing.get('title', listing)}")


def main() -> None:
    listings = load_listings()

    with requests.Session() as session:
        session.headers.update({"Authorization": f"Bearer {API_KEY}"})
        for listing in listings:
            upload_listing(session, listing)

    print(f"Done: {len(listings)} listing(s) uploaded.")


if __name__ == "__main__":
    main()
