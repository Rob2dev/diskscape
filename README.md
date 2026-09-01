# diskscape

Een kleine, dependency-vrije disk usage visualizer in Python: een treemap
die laat zien waar je schijfruimte heen gaat.

## Features

- Kies bij het opstarten een schijf/drive uit een lijst (drive letters op
  Windows, mount points op Linux/macOS) - geen folder-browser
- Parallelle scan: meerdere mappen tegelijk uitgelezen via een
  thread-pool (I/O-bound syscalls laten de GIL los, dus dit helpt vooral
  op netwerkschijven of trage disks)
- Live preview tijdens het scannen: het canvas wordt elke 500ms
  herbouwd op basis van wat er al bekend is. Mappen die nog niet klaar
  zijn met scannen krijgen een grijs vlak met "?" in plaats van een
  grootte, zodat je meteen structuur ziet verschijnen in plaats van naar
  een lege balk te staren
- Voortgangsbalk met percentage en ETA tijdens het scannen. Bij een
  schijf-scan gebruikt hij het bekende "in gebruik"-totaal (via
  disk_usage) als noemer; bij een los pad zonder bekend totaal toont hij
  een indeterminate balk met verstreken tijd en bytes gescand
- Geneste treemap, SpaceMonger/WinDirStat-stijl: submappen worden tot
  meerdere niveaus diep getekend binnen hun oudermap (zolang er
  plaats is), elk met een eigen naam/grootte-caption
- Elk zichtbaar blok - bestand of map, op elk niveau - is klikbaar: klik
  om in die map te zoomen, Backspace / "Back" om terug te gaan
- Kleurcodering: mappen krijgen een vast blauwtintje per nesting-diepte
  (zoals SpaceMonger), bestanden krijgen een verzadigde, over de hele
  kleurencirkel gespreide kleur per extensie (stabiel per type)
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
