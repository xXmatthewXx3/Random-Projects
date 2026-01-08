import os
import argparse
from dotenv import load_dotenv
from gsmservice_gateway import Client

def action_check_credits(client):
    try:
        res = client.accounts.get()
        if res:
            print(f"Stan Konta: {res.credit} {res.currency}")
        else:
            print("Nie udało się pobrać danych konta.")
    except Exception as e:
        print(f"Błąd API: {e}")

def action_check_cost(client, args):
    sender = args.check_cost[0]
    recipients_str = args.check_cost[1]
    message = args.check_cost[2]

    recipients_list = [num.strip() for num in recipients_str.split(',')]

    try:
        res = client.outgoing.sms.get_price(request=[
            {
                "recipients": recipients_list,
                "message": message,
                "sender": sender,
                "type": 1,
                "unicode": True,
                "flash": args.flash,
                "date_": None,
            },
        ])
        
        if res and res.result:
            total_price = sum(item.price for item in res.result)
            
            print(f"Liczba odbiorców: {len(res.result)}")
            print(f"Łączny koszt: {total_price:.2f} PLN")
        else:
            print("Brak danych o cenie.")
            
    except Exception as e:
        print(f"Błąd podczas sprawdzania ceny: {e}")

def action_send_sms(client, args):
    sender = args.send_sms[0]
    recipients_str = args.send_sms[1]
    message = args.send_sms[2]

    # Obsługa wielu numerów po przecinku
    recipients_list = [num.strip() for num in recipients_str.split(',')]

    print(f"Wysyłam wiadomość do {len(recipients_list)} odbiorców...")

    try:
        res = client.outgoing.sms.send(request=[
            {
                "recipients": recipients_list,
                "message": message,
                "sender": sender,
                "type": 1,
                "unicode": True,
                "flash": args.flash,
                "date_": None,
            },
        ])

        if res and res.result:
            print(f"\n--- Raport wysyłki ---")
            for msg in res.result:
                if getattr(msg, 'error', None):
                    print(f"[BŁĄD] {msg.recipient}: {msg.error}")
                else:
                    print(f"[OK] {msg.recipient}")
                    print(f"     Status: {msg.status_code} ({msg.status_description})")
                    print(f"     ID: {msg.id}")
                    print(f"     Koszt: {msg.price} PLN")
        else:
            print("Brak danych w odpowiedzi od bramki.")

    except Exception as e:
        print(f"Krytyczny błąd podczas wysyłania: {e}")


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="GSM Communication Tool")

    parser.add_argument("--key", help="Klucz API", default=os.getenv("GATEWAY_API_BEARER", ""))
    parser.add_argument("--check-credits", action ="store_true")
    parser.add_argument("--send-sms", nargs=3, metavar=('Sender', 'Number', 'Message'), help="Send message")
    parser.add_argument("--check-cost", nargs=3, metavar=('Sender', 'Number', 'Message'), help="Check cost")
    parser.add_argument("--flash", action="store_true", help="Flash SMS flag")

    args = parser.parse_args()

    s = Client(
        bearer=args.key,
    )

    if args.check_credits:
        action_check_credits(s)
    
    if args.check_cost:
        action_check_cost(s, args)

    if args.send_sms:
        action_send_sms(s, args)

if __name__ == "__main__":
    main()