import traceback
from datetime import datetime
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
from compute_session import MockComputeSession

app = Flask(__name__)
db = firestore.Client()


@app.route("/")
def index():
    transactions = [
        transaction.to_dict() for transaction in db.collection("transactions").stream()
    ]
    transactions.sort(key=lambda transaction: transaction["timestamp"], reverse=True)
    cards = [card.to_dict() for card in db.collection("cards").stream()]
    # @TODO(darrennchan8): Consider refactoring cards into a simple dictionary in the backend.
    cards = {card["number"]: card["name"] for card in cards}
    transactions = [
        {
            **transaction,
            "timestamp": transaction["timestamp"].strftime("%x %X"),
            "card": cards.get(
                transaction["card"], f"**** **** **** {transaction['card'][-4:]}"
            ),
            "amount": "${:,.2f}".format(transaction["amount"]),
        }
        for transaction in transactions
    ]
    return render_template("status.html", transactions=transactions, cards=cards)


def reload_batch(cards, amount):
    results = []
    with MockComputeSession("127.0.0.1") if app.debug else ComputeSession(
        "standalone-chrome"
    ) as session:
        with AmazonBalanceReloader(
            f"{session.remote_ip()}:4444", headless=not app.debug
        ) as reloader:
            try:
                credentials = (
                    db.collection("credentials").document("amazon").get().to_dict()
                )
                reloader.authenticate(credentials["username"], credentials["password"])
            except AmazonBalanceReloaderException:
                traceback.print_exc()
            for card in cards:
                timestamp_start = datetime.now()
                try:
                    reloader.reload(card, amount)
                    results.append(
                        {
                            "timestamp": timestamp_start,
                            "card": card,
                            "amount": amount,
                            "success": True,
                            "message": "Success!",
                        }
                    )
                except AmazonBalanceReloaderException as inst:
                    results.append(
                        {
                            "timestamp": timestamp_start,
                            "card": card,
                            "amount": amount,
                            "success": False,
                            "message": str(inst),
                        }
                    )
                    traceback.print_exc()
    return results


@app.route("/reload")
def reload():
    try:
        amount = float(request.args.get("amount"))
    except (TypeError, ValueError):
        raise BadRequest()
    card = request.args.get("card")
    if amount <= 0 or card is None or not match(r"^\d{16}$", card):
        raise BadRequest()
    result = reload_batch([card], amount)[0]
    db.collection("transactions").add(result)
    return jsonify(result)


@app.route("/reloadAll")
def reload_all():
    try:
        amount = float(request.args.get("amount"))
    except (TypeError, ValueError):
        raise BadRequest()
    if amount <= 0:
        raise BadRequest()
    cards = [card.to_dict()["number"] for card in db.collection("cards").stream()]
    results = reload_batch(cards, amount)
    for result in results:
        db.collection("transactions").add(result)
    # @TODO(darrennchan8): Consider obfuscating (use alias) the resulting array of card numbers.
    return jsonify(results)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug="--prod" not in argv)
