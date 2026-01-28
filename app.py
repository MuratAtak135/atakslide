import os
import json
import base64
import fitz  # PyMuPDF
from flask import Flask, render_template, request
from openai import OpenAI
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

load_dotenv()

app = Flask(__name__)

# --- DEĞİŞİKLİK BURADA: Tam dosya yolu (Absolute Path) tanımlandı ---
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static/uploads')
# --------------------------------------------------------------------

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def analyze_image_content(image_path, filename):
    try:
        base64_image = encode_image(image_path)
        # Analiz için token limitini düşük tutuyoruz (hız için)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Bu görselde ne var? Konusunu 1 cümle ile özetle."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ],
            max_completion_tokens=4000
        )
        return f"DOSYA ADI: '{filename}' -> İÇERİK: {response.choices[0].message.content}"
    except:
        return f"DOSYA ADI: '{filename}' -> Analiz edilemedi."


def process_uploaded_pdf(filepath):
    full_text, saved_images = "", []
    try:
        doc = fitz.open(filepath)
        base_filename = os.path.splitext(os.path.basename(filepath))[0]
        for i, page in enumerate(doc):
            t = page.get_text()
            if t: full_text += f"\n--- SAYFA {i + 1} ---\n{t}\n"
            for idx, img in enumerate(page.get_images(full=True)):
                try:
                    xref = img[0]
                    base = doc.extract_image(xref)
                    # Çok küçük ikonları filtrele (2KB altı)
                    if len(base["image"]) > 2048:
                        name = f"{base_filename}_p{i + 1}_i{idx + 1}.{base['ext']}"
                        with open(os.path.join(app.config['UPLOAD_FOLDER'], name), "wb") as f:
                            f.write(base["image"])
                        saved_images.append(name)
                except:
                    continue
        doc.close()
    except:
        pass
    return str(full_text), saved_images


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        try:
            user_prompt = request.form.get('user_prompt')
            selected_theme = request.form.get('theme', 'default')
            ui_language = request.form.get('ui_language', 'tr')  # Dil seçimi alındı
            f = request.files.get('file_upload')

            if not user_prompt and (not f or f.filename == ''):
                return render_template('index.html', error="Lütfen bir konu yazın veya dosya yükleyin.")

            txt, imgs, analyses = "", [], []
            if f and allowed_file(f.filename):
                fn = secure_filename(f.filename)
                fp = os.path.join(app.config['UPLOAD_FOLDER'], fn)
                f.save(fp)
                if fn.endswith('.pdf'):
                    t, i = process_uploaded_pdf(fp)
                    txt, imgs = t, i
                else:
                    imgs.append(fn)
                    txt = "Kullanıcı görsel yükledi."

            # Görselleri analiz et
            for i in imgs[:15]:  # Limit artırıldı
                analyses.append(analyze_image_content(os.path.join(app.config['UPLOAD_FOLDER'], i), i))

            final_content = f"KULLANICI TALİMATI: {user_prompt}\n"
            if txt: final_content += f"EK KAYNAK METNİ:\n{txt[:20000]}\n"  # Okuma limiti artırıldı

            if analyses: final_content += f"KULLANILABİLİR GÖRSELLER VE İÇERİKLERİ:\n" + "\n".join(
                analyses)

            # --- SİSTEM TALİMATI (AYNI KALDI) ---
            sys_prompt = """
            Sen profesyonel, detaycı ve akademik bir sunum tasarımcısısın.

            GÖREVİN:
            Verilen konuyu ve görselleri kullanarak EN AZ 10 SLAYTLIK kapsamlı bir sunum hazırla.

            Kullanıcının girdiği 'KULLANICI TALİMATI' hangi dildeyse (Türkçe, İngilizce, vb.), sunumun tüm içeriğini (başlıklar, metinler, maddeler) KESİNLİKLE O DİLDE oluştur. Talimat İngilizce ise çıktı %100 İngilizce olmalıdır.

            1. GÖRSEL YERLEŞİMİ (STRICT RULE):
               - Sana verilen 'KULLANILABİLİR GÖRSELLER VE İÇERİKLERİ' listesine bak.
               - Her slayt oluşturduğunda, o slaytın konusunu analiz et.
               - Eğer listedeki bir görselin içeriği slaytın konusuyla DOĞRUDAN ALAKALIYSA o görseli kullan.
               - Görsel eşleşmesi yaparken dosya adını JSON'daki 'image' alanına yaz.
               - Görselleri mümkün olduğunca çok slaytta kullanmaya çalış.

            2. LAYOUT SEÇİMİ VE METİN DENGESİ (ÇOK ÖNEMLİ):
               - 'big_image' KULLANMA.
               - Slaytlar ne boş kalsın ne de taşacak kadar dolsun. Şu kurallara uy:

               * 'standard_split' (İki Sütun): Konuyu iki alt başlığa böl (Örn: Avantajlar/Dezavantajlar). Her sütuna 4-5 cümleden oluşan DOYURUCU birer paragraf yaz. (Yaklaşık 60-80 kelime).
               * 'standard' (Tek Blok): Konuyu tek bir akışta anlat. En fazla 5-6 cümleden oluşan güçlü bir paragraf yaz. (Yaklaşık 80-90 kelime).
               * 'features' (3 Sütun): Sadece 3 madde. Her madde altına 2 cümlelik açıklama.
               * 'cards' (Kartlar): Maksimum 6 kart. Her kart kısa ve öz olmalı.
               * 'numbered_list' (Liste): Maksimum 5 madde.

            3. İÇERİK YOĞUNLUĞU:
               - "Çok kısa yaz" DEMİYORUM. "Tasarımı patlatacak kadar yazma" DİYORUM.
               - Akademik dil kullan, boş laf yapma, bilgi ver.

            4. SLAYT YAPISI VE KAPAK:
               - En az 5 slayt olacak.
               - SLAYT 1 kesinlikle 'title_slide' olacak.
               - SLAYT 1'in 'title' alanına SUNUMUN GERÇEK KONUSU/ANA BAŞLIĞI yazılmalıdır.
               - SLAYT 1'de sadece ana başlık olsun. Alt başlık olmasın.

            Çıktı JSON Formatı:
            {
                "presentation_title": "Sunum Başlığı",
                "slides": [
                    { 
                        "title": "Sunumun Gerçek Ana Başlığı", 
                        "layout": "title_slide", 
                        "content": ["Sunum Özeti..."], 
                        "image": "dosya_adi.jpg" 
                    },
                    { 
                        "title": "Giriş", 
                        "layout": "standard_split", 
                        "content": ["Paragraf 1 içeriği...", "Paragraf 2 içeriği..."], 
                        "image": "dosya_adi.jpg" 
                    }
                ]
            }
            """

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": final_content}
                ],
                response_format={"type": "json_object"},
                max_completion_tokens=5000
            )

            presentation_data = json.loads(response.choices[0].message.content)
            presentation_data['theme'] = selected_theme

            # Dil seçeneğini viewer'a gönderiyoruz
            return render_template('viewer.html', data=presentation_data, ui_language=ui_language)

        except Exception as e:
            return render_template('index.html', error=f"Hata: {str(e)}")

    return render_template('index.html')


if __name__ == '__main__':
    app.run(debug=True)