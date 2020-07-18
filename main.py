import traceback
from datetime import datetime
from datetime import timezone
from functools import lru_cache
from re import match
from sys import argv

from flask import Flask
from flask import jsonify
from flask import render_template
from flask import request
from google.cloud import firestore
from werkzeug.exceptions import BadRequest

from amazon_balance_reloader import AmazonBalanceReloader
from amazon_balance_reloader import AmazonBalanceReloaderException
from compute_session import ComputeSession
from compute_session import ComputeSessionException
from compute_session import is_app_engine_environment
from compute_session import MockComputeSession

app = Flask(__name__)
db = firestore.Client()


@lru_cache
def masked_card(card_num):
    cards = [card.to_dict() for card in db.collection("cards").stream()]
    cards = {card["number"]: card["name"] for card in cards}
    return cards.get(card_num, f"**** **** **** {card_num[-4:]}")


@app.route("/")
def index():
    transactions = [
        transaction.to_dict() for transaction in db.collection("transactions").stream()
    ]
    transactions.sort(
        key=lambda transaction: transaction["timestamp_end"], reverse=True
    )
    transactions = [
        {
            "timestamp": transaction["timestamp_start"].strftime("%x %X"),
            "time_elapsed": f'{round((transaction["timestamp_end"] - transaction["timestamp_start"]).total_seconds())} seconds',
            "app_engine": transaction["app_engine"],
            "compute_engine": transaction["compute_engine"],
            "cards": [masked_card(card) for card in transaction["cards"]],
            "amount": "${:,.2f}".format(transaction["amount"]),
            "success": transaction["success"],
            "message": f'Some cards failed to reload: { ", ".join(masked_card(cs[0]) for cs in zip(transaction["cards"], transaction["success"]) if not cs[1]) }'
            if True in transaction["success"] and False in transaction["success"]
            else f'Successfully reloaded {len(transaction["cards"])} cards!'
            if True in transaction["success"]
            else f'Failed to reload {len(transaction["cards"])} cards!',
        }
        for transaction in transactions
    ]
    cards = [card.to_dict() for card in db.collection("cards").stream()]
    cards = {card["name"]: f'**** **** **** {card["number"][-4:]}' for card in cards}
    return render_template("status.html", transactions=transactions, cards=cards)


def reload_batch(cards, amount):
    result = {
        "timestamp_start": datetime.now(timezone.utc),
        "app_engine": is_app_engine_environment(),
        "compute_engine": not app.debug,
        "cards": cards,
        "amount": amount,
        "success": [],
        "timestamp_end": None,
    }
    try:
        with ComputeSession("standalone-chrome") if result[
            "compute_engine"
        ] else MockComputeSession("127.0.0.1") as session:
            with AmazonBalanceReloader(
                f"{session.remote_ip()}:4444", headless=result["compute_engine"]
            ) as reloader:
                credentials = (
                    db.collection("credentials").document("amazon").get().to_dict()
                )
                reloader.authenticate(credentials["username"], credentials["password"])
                for card in cards:
                    try:
                        reloader.reload(card, amount)
                        result["success"].append(True)
                    except AmazonBalanceReloaderException:
                        result["success"].append(False)
                        traceback.print_exc()
    except (ComputeSessionException, AmazonBalanceReloaderException):
        result["success"].extend([False] * (len(cards) - len(result["success"])))
        traceback.print_exc()
    result["timestamp_end"] = datetime.now(timezone.utc)
    db.collection("transactions").add(result)
    return result


@app.route("/reload")
def reload():
    try:
        amount = float(request.args.get("amount"))
    except (TypeError, ValueError):
        raise BadRequest()
    cards = request.args.get("cards")
    if amount <= 0 or cards is None or not match(r"^\d{16}(,\d{16})*$", cards):
        raise BadRequest()
    return jsonify({**reload_batch(cards.split(","), amount), "cards": None})


@app.route("/reloadAll")
def reload_all():
    try:
        amount = float(request.args.get("amount"))
    except (TypeError, ValueError):
        raise BadRequest()
    if amount <= 0:
        raise BadRequest()
    cards = [card.to_dict()["number"] for card in db.collection("cards").stream()]
    # @TODO(darrennchan8): Consider obfuscating (use alias) the resulting array of card numbers.
    return jsonify({**reload_batch(cards, amount), "cards": None})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug="--prod" not in argv)
