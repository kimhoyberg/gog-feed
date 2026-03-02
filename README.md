# 🚐 Viborg Caravan Center - Automatisk GoG XML Feed

Dette script synkroniserer automatisk lageret fra Framer CMS til GulogGratis (GoG) én gang i timen via GitHub Actions.

## 🛠 Sådan virker det
1. **Kilde:** Scriptet besøger `viborg-caravancenter.dk/data-eksport`.
2. **Logik:** Scriptet (`feed.py`) læser de 8 tekstfelter i hver "Stack" og grupperer dem.
3. **Output:** En `feed.xml` genereres i mappen `public/`, som GoG læser fra.

## ⚠️ Regler for Framer (De 8 Hellige Felter)
Scriptet tæller tekststykker. Derfor må rækkefølgen i din Framer-stack **aldrig** ændres:
1. **Slug** (ID)
2. **Type** (Skal indeholde "Campingvogn")
3. **Model** (Navn)
4. **År** (Årgang)
5. **Pris**
6. **Egenvægt** (SKAL stå før totalvægt)
7. **Totalvægt**
8. **Kategori** (Ny/Brugt)

## 🤖 Automatisering
* **Interval:** Kører hver hele time (via `.github/workflows/main.yml`).
* **Hukommelse:** Scriptet fjerner automatisk dubletter (mobil/desktop versioner fra Framer).
* **Vægt-fix:** Scriptet bytter om på Egen/Total i XML-filen, så GoG læser det korrekt.

## 📝 Vedligeholdelse
Hvis feedet stopper med at opdatere:
- Tjek **Actions** fanen her på GitHub for fejl.
- Tjek om rækkefølgen af felter i Framer er blevet ændret.
