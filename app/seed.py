from .extensions import db

HONEYMOON_PAYMENT_URL = "https://link.mercadopago.com.br/viniciussousa"

def seed_gifts():
    from .models import Gift
    if Gift.query.first():
        return
    defaults = [
        ("Buddemeyer Jogo de toalhas Doris Banho Cinza/Cinza Claro 5 peças", "Sugestão de presente. Confira preço e disponibilidade na loja.", "https://a.co/d/0gGuAo8p", "🧺"),
        ("Zojirushi Garrafa térmica premium, 1 litro, aço inoxidável escovado", "Sugestão de presente. Confira preço e disponibilidade na loja.", "https://a.co/d/03jbW8Ei", "☕"),
        ("Jogo de Assadeiras 3 Peças Portuguesa Retangular Havan Casa - Branco", "Sugestão de presente. Confira preço e disponibilidade na loja.", "https://www.havan.com.br/jogo-de-assadeiras-retangular-portuguesa-havan-casa-3-pecas-branco/p", "🍽️"),
    ]
    for title, description, link, emoji in defaults:
        db.session.add(Gift(title=title, description=description, external_url=link,
                            amount_cents=0, emoji=emoji, gift_type="marketplace"))
    if not Gift.query.filter_by(gift_type="honeymoon").first():
        db.session.add(Gift(title="Cota para lua de mel", description="Presenteie por Pix ou cartão de crédito e faça parte da nossa viagem.", amount_cents=0, emoji="🌴", gift_type="honeymoon", external_url=HONEYMOON_PAYMENT_URL))
    db.session.commit()
