import os
import imaplib
import email
from email.header import decode_header
import time
import requests
import re

# ====================================
# CONFIGURAÇÕES (via variáveis de ambiente)
# ====================================
EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
IMAP_SERVER = os.environ.get("IMAP_SERVER", "imap.skymail.net.br")
IMAP_PORT = int(os.environ.get("IMAP_PORT", "993"))
EMAIL_FOLDER = os.environ.get("EMAIL_FOLDER", "INBOX")

WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "5"))

# ====================================
# FUNÇÕES
# ====================================

def connect_to_email():
    """Conecta ao servidor IMAP"""
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        mail.select(EMAIL_FOLDER)
        print(f"✅ Conectado ao email: {EMAIL_ADDRESS}")
        return mail
    except Exception as e:
        print(f"❌ Erro ao conectar: {e}")
        return None


def decode_email_subject(subject):
    """Decodifica o assunto"""
    if subject is None:
        return ""
    decoded = decode_header(subject)
    parts = []
    for content, encoding in decoded:
        if isinstance(content, bytes):
            parts.append(content.decode(encoding or "utf-8", errors="ignore"))
        else:
            parts.append(content)
    return "".join(parts)


def get_email_html(msg):
    """Extrai corpo HTML ou converte texto para HTML"""
    html_body = ""
    text_body = ""

    if msg.is_multipart():
        for part in msg.walk():
            try:
                content_type = part.get_content_type()
                payload = part.get_payload(decode=True)
                if not payload:
                    continue

                decoded = payload.decode("utf-8", errors="ignore")

                if content_type == "text/html":
                    html_body = decoded
                elif content_type == "text/plain" and not html_body:
                    text_body = decoded

            except:
                pass
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            decoded = payload.decode("utf-8", errors="ignore")
            if msg.get_content_type() == "text/html":
                html_body = decoded
            else:
                text_body = decoded

    if not html_body and text_body:
        html_body = f"<html><body><pre>{text_body}</pre></body></html>"

    return html_body.strip()


def parse_email_to_json(msg):
    """Converte email em JSON para o Webhook"""
    subject = decode_email_subject(msg["Subject"])
    from_email = msg.get("From", "")

    # Extrair apenas o e-mail (remover nome se houver)
    match = re.search(r'<(.+?)>|([^\s<>]+@[^\s<>]+)', from_email)
    clean_from = match.group(1) or match.group(2) if match else from_email

    html_body = get_email_html(msg)

    return {
        "subject": subject,
        "from": clean_from.strip(),
        "html": html_body
    }


def send_to_webhook(email_data):
    """Envia JSON ao Webhook"""
    try:
        response = requests.post(
            WEBHOOK_URL,
            json=email_data,
            headers={"Content-Type": "application/json"},
            timeout=10
        )

        if response.status_code == 200:
            print(f"🚀 Webhook enviado: {email_data['subject']}")
            return True

        print(f"⚠️ Erro {response.status_code}: {response.text}")
        return False

    except Exception as e:
        print(f"❌ Erro webhook: {e}")
        return False


# ====================================
# LOOP PRINCIPAL — APENAS EMAILS NÃO LIDOS
# ====================================
def monitor_emails():
    print("🔥 Monitoramento iniciado...")
    print(f"🔗 Webhook: {WEBHOOK_URL}")

    mail = connect_to_email()
    if not mail:
        return

    while True:
        try:
            # Busca *somente* emails não lidos (UNSEEN)
            status, data = mail.search(None, "UNSEEN")

            if status == "OK":
                email_ids = data[0].split()

                if email_ids:
                    print(f"📬 {len(email_ids)} email(s) novo(s) não lido(s)")

                for email_id in email_ids:
                    status, msg_data = mail.fetch(email_id, "(RFC822)")

                    if status != "OK":
                        print(f"❌ Erro ao buscar email {email_id}")
                        continue

                    raw_email = msg_data[0][1]
                    msg = email.message_from_bytes(raw_email)

                    email_json = parse_email_to_json(msg)
                    print(f"\n📨 {email_json['subject'][:60]}")

                    if send_to_webhook(email_json):
                        # Marca como LIDO para não processar novamente
                        mail.store(email_id, "+FLAGS", "\\Seen")
                        print("✔️ Marcado como lido\n")

            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            print(f"❌ Erro no loop: {e}")
            time.sleep(5)
            mail = connect_to_email()


if __name__ == "__main__":
    monitor_emails()
