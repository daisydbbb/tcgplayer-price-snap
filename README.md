# TCGplayer Price Snap

Scrape the 3 lowest listing prices (price + shipping, English-language only)
for a TCGplayer product — as a one-off CLI lookup or a small local web app
that also supports bulk lookups from a CSV/Excel file.

## Requirements

- Python 3.10+
- Google Chrome installed (Selenium drives it directly; Selenium 4.6+
  auto-manages the matching chromedriver for you)

```bash
pip install -r requirements.txt
```

## CLI usage

```bash
python3 scrape_tcgplayer.py "<tcgplayer product url>"
```

Example:

```
Product: Mr.3(Galdino) (056) (Alternate Art) - The Time of Battle (OP16)
Number/Rarity: OP16-056(SR)

1. Total: $37.31  (price $36.00 + shipping $1.31)  [Near Mint Foil]  seller: dbestcollectibles
2. Total: $37.98  (price $36.99 + shipping $0.99)  [Near Mint Foil]  seller: TCG Trove LLC
3. Total: $37.99  (price $37.99 + shipping $0.00)  [Near Mint Foil]  seller: RnR Gaming LLC
```

## Web app

```bash
python3 app.py
```

Then open **http://127.0.0.1:5001**.

- **Snap** — paste a single TCGplayer product link, results appear in the
  panel on the right.
- **Snap All** — upload a CSV or Excel file with (at minimum) a link in
  Column B; a filled-in copy downloads automatically once done. See
  `examples/product_template.xlsx` for the expected layout — the app adds
  any of the `Full Name` / `Number` / `Price1-3` / `Time` columns that
  aren't already present.

## Notes

- Port 5000 is skipped in favor of 5001 because macOS Control Center
  (AirPlay Receiver) claims port 5000 by default on most Macs.
- Listings are filtered to English only; sealed/non-card products don't
  always expose a `Number`/`Rarity` field, in which case that field is
  simply omitted from the output.
