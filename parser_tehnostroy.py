import csv 
import re 
import time 
from datetime import datetime
from urllib.parse import urljoin 
from xml.etree import ElementTree as ET
from xml.dom import minidom 
import requests
from bs4 import BeautifulSoup 

base_url = 'https://tehnostroy.by'
headers  = {
    'User-Agent' : (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

delay = 1.0

categories = {
    "Кровельные системы": [
        "/katalog/krovelnye-sistemy/ventilyaciya-krovli/",
        "/katalog/krovelnye-sistemy/teploizodyaciya/pir-plita-pir-paneli/",
        "/katalog/krovelnye-sistemy/teploizodyaciya/kamennaya-vata/",
        "/katalog/krovelnye-sistemy/teploizodyaciya/steklovata/",
        "/katalog/krovelnye-sistemy/teploizodyaciya/ekstrudirovannyj-penopostirol-xps/",
        "/katalog/krovelnye-sistemy/gidroizolyaciya/rulonnaya-gidroizolyaciya/",
        "/katalog/krovelnye-sistemy/gidroizolyaciya/voronki-vodostochnye-dlya-krovli/",
        "/katalog/krovelnye-sistemy/gidroizolyaciya/geotekstil/",
        "/katalog/krovelnye-sistemy/gidroizolyaciya/pvh-membrany/",
        "/katalog/krovelnye-sistemy/paroizolyaciya-i-vetrozashhita/",
        "/katalog/krovelnye-sistemy/planki/planki-karniznye/",
        "/katalog/krovelnye-sistemy/planki/planki-torcevye/",
        "/katalog/krovelnye-sistemy/planki/planki-primykaniya/",
        "/katalog/krovelnye-sistemy/rulonnye-krovelnye-materialy/",
        "/katalog/krovelnye-sistemy/mastiki-i-prajmery/",
    ],
    "Фасадные системы": [
        "/katalog/fasadnye-sistemy/teploizodyaciya/pir/",
        "/katalog/fasadnye-sistemy/teploizodyaciya/kamennaya-vata/",
        "/katalog/fasadnye-sistemy/teploizodyaciya/steklovata/",
        "/katalog/fasadnye-sistemy/teploizodyaciya/ekstrudirovannyj-penopolistirol-xps/",
        "/katalog/fasadnye-sistemy/paroizolyaciya-i-vetrozashhita/",
    ],
    "Фундамент": [
        "/katalog/fundament/gidroizolyaciya/",
        "/katalog/fundament/teploizolyaciya/",
        "/katalog/fundament/armatura/",
        "/katalog/fundament/mastiki-i-prajmery/",
    ],
    "Сопутствующие материалы": [
        "/katalog/soputstvuyushhie-materialy/montazhnye-peny/",
        "/katalog/soputstvuyushhie-materialy/ochistiteli/",
        "/katalog/soputstvuyushhie-materialy/germetiki-obshhestroitelnye/",
        "/katalog/soputstvuyushhie-materialy/klei/",
        "/katalog/soputstvuyushhie-materialy/gvozdi/",
        "/katalog/soputstvuyushhie-materialy/dyubeli/",
    ]
}
category_ids = {name: str(i + 1) for i,name in enumerate(categories.keys())}

def get_soup(url):
    resp = requests.get(url,headers=headers, timeout=15)
    resp.raise_for_status()
    resp.encoding = 'utf-8'
    return BeautifulSoup(resp.text, 'html.parser')

def get_product_links(category_url: str):
    soup = get_soup(category_url)
    links = set()
    for a in soup.find_all("a",class_="product__header", href=True):
        href = urljoin(base_url, a["href"])
        links.add(href)
    return links


def parse_char(soup):
    chars = {}
    table = soup.find('table',class_="styled-table")
    if table:
        for row in table.find_all('tr'):
            cells = row.find_all(['td','th'])
            if len(cells) >= 2:
                key = cells[0].get_text(strip=True).rstrip(':')
                value = cells[1].get_text(strip=True)
                if key and value:
                    chars[key] = value
    return chars

def parse_description(soup):
    parts = []
    for p in soup.find_all("p"):
        text = p.get_text(" ", strip=True)
        if len(text) < 40:
            continue
        if any(x in text.lower() for x in ["корзине", "каталог", "доставка"]):
            continue
        parts.append(text)
    return " ".join(parts)


def parse_product(url, section):
    soup = get_soup(url)
    name_tag = soup.find("h1")
    name = name_tag.get_text(strip=True) if name_tag else ""
    text = soup.get_text(" ", strip=True)

    m = re.search(r"(VK-\w+|\d{3,})", text)
    sku = m.group(1) if m else ""

    brands = ["Технониколь", "POLIVENT", "Optima"]
    brand = next((b for b in brands if b.lower() in text.lower()), "")

    text = text.lower()
    if "есть в наличии" in text:
        availability = "есть в наличии"
    elif "под заказ" in text:
        availability = "под заказ"
    else:
        availability = ""

    m = re.search(r"(\d+[.,]\d{2})", text)
    price = m.group(1).replace(",", ".") if m else ""

    images = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if not src:
            continue
        if any(x in src.lower() for x in ["logo", "icon", "svg"]):
            continue
        if not src.startswith("http"):
            src = urljoin(base_url, src)
        if any(ext in src.lower() for ext in [".webp", ".png", ".jpg", ".jpeg"]):
            images.append(src)
    images = list(dict.fromkeys(images))

    data = {
        "section": section,
        "url": url,
        "name": name,
        "sku": sku,
        "brand": brand,
        "price": price,
        "currency": "BYN",
        "availability": availability,
        "images": "; ".join(images),
        "description": parse_description(soup),
    }
    data.update(parse_char(soup))
    return data


def save_csv(products, path: str = "products.csv"):
    base_fields = [
        "section", "url", "name", "sku", "brand",
        "price", "currency", "availability", "images", "description",
    ]
    extra = set()
    for p in products:
        extra.update(k for k in p if k not in base_fields)
    fieldnames = base_fields + sorted(extra)

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames,
                                quoting= csv.QUOTE_ALL, escapechar='\\')
        writer.writeheader()
        writer.writerows(products)

def save_yml(products, path: str = "products.yml"):
    root = ET.Element("yml_catalog", date=datetime.now().strftime("%Y-%m-%d %H:%M"))
    shop = ET.SubElement(root, "shop")
    ET.SubElement(shop, "name").text = "tehnostroy.by"
    ET.SubElement(shop, "company").text = "ТД «ТЕХНОстрой»"
    ET.SubElement(shop, "url").text = base_url
    currencies = ET.SubElement(shop, "currencies")
    ET.SubElement(currencies, "currency", id="BYN", rate="1")
    categories_el = ET.SubElement(shop, "categories")
    for name, cid in category_ids.items():
        ET.SubElement(categories_el, "category", id=cid).text = name
    offers_el = ET.SubElement(shop, "offers")

    for i, p in enumerate(products, start=1):
        offer_id = p["sku"] or f"item-{i}"
        offer = ET.SubElement(
            offers_el, "offer", id=offer_id,
            available="true" if p["availability"] != "под заказ" else "false",
        )
        ET.SubElement(offer, "url").text = p["url"]
        if p["price"]:
            ET.SubElement(offer, "price").text = p["price"]
        ET.SubElement(offer, "currencyId").text = "BYN"
        ET.SubElement(offer, "categoryId").text = category_ids.get(p["section"], "1")
        for img in p["images"].split("; "):
            if img:
                ET.SubElement(offer, "picture").text = img
        ET.SubElement(offer, "name").text = p["name"]
        if p["brand"]:
            ET.SubElement(offer, "vendor").text = p["brand"]
        if p["description"]:
            ET.SubElement(offer, "description").text = p["description"]
        for key, value in p.items():
            if key not in (
                "section", "url", "name", "sku", "brand", "price",
                "currency", "availability", "images", "description",
            ):
                ET.SubElement(offer, "param", name=key).text = value
    rough = ET.tostring(root, encoding="utf-8")
    pretty = minidom.parseString(rough).toprettyxml(indent="  ", encoding="utf-8")
    with open(path, "wb") as f:
        f.write(pretty)

def main():
    all_products = []
    for section, cat_paths in categories.items():
        for cat_path in cat_paths:
            cat_url = urljoin(base_url, cat_path)
            print(f"Категория: {cat_url}")
            links = set(get_product_links(cat_url))
            print(f"  найдено ссылок: {len(links)}")

            for link in links:
                time.sleep(delay)
                try:
                    product = parse_product(link, section)
                    all_products.append(product)
                    print(f"    | {product['name']} ({product['price']} BYN)")
                except Exception as e:
                    print(f"    ошибка на {link}: {e}")
    save_csv(all_products)
    save_yml(all_products)
    print(f"\nГотово: {len(all_products)} товаров -> products.csv, products.yml")

if __name__ == "__main__":
    main()