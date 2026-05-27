"""Envio de EPUB para o Kindle via e-mail (SMTP async).

A Amazon aceita .epub direto pelo "Send to Kindle" por e-mail: basta mandar
o arquivo como anexo para o endereco @kindle.com, de um remetente aprovado.
"""

from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

import aiosmtplib

from app.logging_conf import get_logger

log = get_logger("kindle")


async def send_epub_to_kindle(
    epub_path: str | Path,
    *,
    host: str,
    port: int,
    username: str | None,
    password: str | None,
    sender: str,
    to: str,
    use_tls: bool = True,
) -> None:
    epub_path = Path(epub_path)
    if not epub_path.exists():
        raise FileNotFoundError(epub_path)

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = epub_path.stem
    msg.set_content("Enviado pelo Novel Scraper to EPUB.")
    msg.add_attachment(
        epub_path.read_bytes(),
        maintype="application",
        subtype="epub+zip",
        filename=epub_path.name,
    )

    await aiosmtplib.send(
        msg,
        hostname=host,
        port=port,
        username=username or None,
        password=password or None,
        start_tls=use_tls,
    )
    log.info("kindle_sent", to=to, file=epub_path.name)
