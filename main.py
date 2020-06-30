import datetime
import re
from enum import Enum

from flask import Flask
from flask import jsonify
from flask import render_template
from flask import request
from google.cloud import firestore
from werkzeug.exceptions import BadRequest

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
                transaction["card"], "**** **** **** " + transaction["card"]
            ),
            "amount": "${:,.2f}".format(transaction["amount"]),
        }
        for transaction in transactions
    ]
    return render_template("status.html", transactions=transactions, cards=cards)


def reload_batch(cards, amount):
    # @TODO(darrennchan8): Implement this.
    return [
        {
            "timestamp": datetime.datetime.now(),
            "card": card,
            "amount": amount,
            "success": False,
            "message": "Web automation not implemented!",
        }
        for card in cards
    ]


@app.route("/reload")
def reload():
    try:
        amount = float(request.args.get("amount"))
    except:
        raise BadRequest()
    card = request.args.get("card")
    if amount <= 0 or card is None or not re.match(r"^\d{4}$", card):
        raise BadRequest()
    result = reload_batch([card], amount)[0]
    db.collection("transactions").add(result)
    return jsonify(result)


@app.route("/reloadAll")
def reload_all():
    try:
        amount = float(request.args.get("amount"))
    except:
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
    app.run(host="127.0.0.1", port=8080, debug=True)
