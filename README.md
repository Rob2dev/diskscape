# diskscape

Een kleine, dependency-vrije disk usage visualizer in Python: een treemap
die laat zien waar je schijfruimte heen gaat.

## Features

- Kies bij het opstarten een schijf/drive uit een lijst (drive letters op
  Windows, mount points op Linux/macOS) - geen folder-browser
- Recursieve scan van de gekozen schijf (loopt in een achtergrondthread,
  UI blijft responsief)
- Squarified treemap layout (Bruls et al., 1999) - zelfgeschreven, geen
  externe dependency nodig
- Klik op een map om erin te zoomen, Backspace / "Back" om terug te gaan
- Kleurcodering per bestandsextensie (stabiel per type, via hash)
- Hover toont volledig pad + grootte in de statusbalk
- "Rescan" om opnieuw te scannen na wijzigingen op schijf

## Vereisten

- Python 3.9+
- Tkinter (zit standaard bij Python op Windows/macOS; op Linux soms
  apart pakket: `sudo apt install python3-tk`)

Geen pip-dependencies nodig.

## Gebruik

```bash
python main.py                # opent een disk-picker
python main.py /pad/naar/map  # scant direct dat pad (optioneel, bv. voor scripting)
python main.py C:\            # Windows: scan direct een schijf
```

## Bestanden

- `disks.py` - schijf/drive-detectie (Windows drive letters, Linux/macOS mount points via /proc/mounts)
- `scanner.py` - recursieve schijfscan naar een Node-boom
- `treemap.py` - squarified treemap layout algoritme (puur Python)
- `main.py` - Tkinter GUI die disk-picker + scanner + treemap samenbrengt

## Bekende beperkingen

- Symlinks worden overgeslagen (voorkomt dubbeltelling / oneindige loops)
- Zeer kleine bestanden/mappen (< 2px in de layout) worden niet getekend
- Geen delete-functionaliteit (bewust: dit is een viewer, geen cleaner)
