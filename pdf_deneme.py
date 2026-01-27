import os
import fitz  # PyMuPDF kütüphanesi

# Görsellerin kaydedileceği geçici klasör
OUTPUT_FOLDER = "deneme_cikti"
if not os.path.exists(OUTPUT_FOLDER):
    os.makedirs(OUTPUT_FOLDER)


def pdf_analiz_et(pdf_yolu):
    print(f"--- '{pdf_yolu}' Analiz Ediliyor ---")

    doc = fitz.open(pdf_yolu)
    tum_metin = ""
    gorsel_sayisi = 0

    for sayfa_no, sayfa in enumerate(doc):
        # 1. Metni Çek
        metin = sayfa.get_text()
        tum_metin += metin + "\n"

        # 2. Görselleri Çek
        gorsel_listesi = sayfa.get_images(full=True)

        for img_index, img in enumerate(gorsel_listesi):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]

            # Görseli dosyaya kaydet
            gorsel_adi = f"sayfa{sayfa_no + 1}_img{img_index + 1}.{image_ext}"
            kayit_yolu = os.path.join(OUTPUT_FOLDER, gorsel_adi)

            with open(kayit_yolu, "wb") as f:
                f.write(image_bytes)

            gorsel_sayisi += 1
            print(f"-> Görsel bulundu ve kaydedildi: {gorsel_adi}")

    print("\n--- SONUÇ ---")
    print(f"Toplam Çıkarılan Görsel: {gorsel_sayisi}")
    print(f"Metin Uzunluğu (Karakter): {len(tum_metin)}")
    print(f"Örnek Metin (İlk 200 karakter):\n{tum_metin[:200]}...")


# --- TEST ALANI ---
# Buraya test etmek istediğin bir PDF dosyasının adını yazmalısın.
# Dosyayı proje klasörüne (app.py'nin yanına) koymayı unutma.
pdf_dosya_adi = "pdfdeneme.pdf"

if os.path.exists(pdf_dosya_adi):
    pdf_analiz_et(pdf_dosya_adi)
else:
    print(f"HATA: '{pdf_dosya_adi}' dosyası bulunamadı. Lütfen proje klasörüne bir PDF koy.")