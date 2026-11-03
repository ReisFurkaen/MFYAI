"""python -m araclar  ->  araç envanterini gösterir (modele bağlanmaz, ağır bir şey yüklemez)."""
from araclar import araclari_yukle, YUKLEME_OZETI, HATALAR

tools = araclari_yukle()
print(f"\nToplam {len(tools)} araç, {len(YUKLEME_OZETI)} dosyada:\n")
for modul, adlar in YUKLEME_OZETI.items():
    print(f"[{modul}.py] {len(adlar)} araç")
    print("   " + ", ".join(adlar))
if HATALAR:
    print("\nYÜKLENEMEYEN DOSYALAR:")
    for modul, hata in HATALAR.items():
        print(f"  - {modul}.py: {hata}")
