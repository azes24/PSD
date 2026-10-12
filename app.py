import json
from pathlib import Path

import altair as alt
import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

# =====================================================================
# KONFIGURASI
# =====================================================================
st.set_page_config(
    page_title="Klasifikasi Tutupan Lahan Jawa Timur",
    page_icon="🛰️",
    layout="wide",
)

BASE = Path(__file__).parent
DATA, ASSETS, MODELS = BASE / "data/data", BASE / "data/assets", BASE / "data/models"

BAND = ["B02", "B03", "B04", "B08", "B11"]
FITUR = BAND + ["NDVI", "NDWI"]
NAMA_MODEL = ["Random Forest", "Naive Bayes", "Decision Tree"]
METRIK = ["Akurasi", "Precision_macro", "Recall_macro", "F1_macro"]

# Warna sama dengan peta di notebook (urutan kelas = urutan abjad model.classes_)
KELAS_DEFAULT = ["Bangunan", "Danau", "Lahan Hijau", "Laut", "Mangrove", "Sawah"]
WARNA_DEFAULT = ["#ff0000", "#0000ff", "#00ff00", "#00ffff", "#800080", "#ffff00"]

INFO_BAND = pd.DataFrame(
    [
        ("B02", "Blue (biru)", "±490 nm", "10 m",
         "Membantu membedakan objek permukaan dan perairan."),
        ("B03", "Green (hijau)", "±560 nm", "10 m",
         "Pantulan hijau; berguna untuk vegetasi dan badan air."),
        ("B04", "Red (merah)", "±665 nm", "10 m",
         "Diserap klorofil, sehingga membedakan vegetasi dari lahan terbuka."),
        ("B08", "NIR (inframerah dekat)", "±842 nm", "10 m",
         "Sangat tinggi pada vegetasi sehat; dasar perhitungan NDVI."),
        ("B11", "SWIR (inframerah gelombang pendek)", "±1.610 nm", "20 m",
         "Peka terhadap kelembapan vegetasi, tanah, dan permukaan lain."),
    ],
    columns=["Band", "Nama", "Panjang gelombang", "Resolusi asli", "Kegunaan"],
)

PENJELASAN_MODEL = {
    "Random Forest": (
        "Gabungan 100 pohon keputusan (`n_estimators=100`). Tiap pohon belajar dari "
        "sebagian data dan sebagian fitur secara acak, lalu hasilnya dipilih "
        "bersama (voting). Biasanya stabil dan tidak mudah terlalu menghafal data latih."
    ),
    "Naive Bayes": (
        "Gaussian Naive Bayes: menganggap tiap fitur berdistribusi normal dan saling "
        "bebas. Asumsi ini jarang terpenuhi pada band satelit (antar band saling "
        "berkorelasi), tetapi modelnya cepat dan sederhana sehingga cocok sebagai pembanding dasar."
    ),
    "Decision Tree": (
        "Satu pohon keputusan yang mengajukan serangkaian pertanyaan ya/tidak pada "
        "nilai fitur (misalnya \"NDWI > 0,1?\") sampai tiba pada satu kelas. Mudah "
        "dibaca, tetapi tanpa batas kedalaman mudah menghafal data latih."
    ),
}


# =====================================================================
# FUNGSI BANTU
# =====================================================================
def tabel(df, **kw):
    """st.dataframe selebar kolom, kompatibel dengan versi Streamlit lama & baru."""
    try:
        st.dataframe(df, width="stretch", **kw)
    except Exception:
        st.dataframe(df, use_container_width=True, **kw)


@st.cache_resource
def muat_model(nama):
    path = MODELS / f"{nama.lower().replace(' ', '_')}.joblib"
    return joblib.load(path) if path.exists() else None


@st.cache_data
def muat_csv(nama_file):
    path = DATA / nama_file
    return pd.read_csv(path) if path.exists() else None


@st.cache_data
def muat_json(nama_file):
    path = DATA / nama_file
    return json.loads(path.read_text()) if path.exists() else None


models = {n: muat_model(n) for n in NAMA_MODEL}
models = {n: m for n, m in models.items() if m is not None}

hasil = muat_csv("hasil_evaluasi.csv")
dataset = muat_csv("dataset_sampel.csv")
laporan = muat_csv("laporan_klasifikasi.csv")
cm_data = muat_json("confusion_matrix.json")
meta = muat_json("peta_meta.json")

if hasil is not None:
    hasil = hasil.sort_values(["F1_macro", "Akurasi"], ascending=False).reset_index(drop=True)

kelas_list = (meta or {}).get("kelas") or (cm_data or {}).get("kelas") or KELAS_DEFAULT
warna_list = (meta or {}).get("warna_hex") or WARNA_DEFAULT
warna = dict(zip(kelas_list, warna_list))


def skala_warna():
    return alt.Scale(domain=list(warna.keys()), range=list(warna.values()))


def gambar_cm(cm, kelas, persen, judul):
    cm = np.array(cm, dtype=float)
    data = cm / np.clip(cm.sum(axis=1, keepdims=True), 1, None) if persen else cm
    n = len(kelas)
    fig, ax = plt.subplots(figsize=(6.4, 5.4))
    ax.imshow(data, cmap="Blues", vmin=0, vmax=1 if persen else None)
    ax.set_xticks(range(n))
    ax.set_xticklabels(kelas, rotation=45, ha="right")
    ax.set_yticks(range(n))
    ax.set_yticklabels(kelas)
    ax.set_xlabel("Prediksi model")
    ax.set_ylabel("Kelas sebenarnya")
    ax.set_title(judul)
    batas = data.max() / 2
    for i in range(n):
        for j in range(n):
            teks = f"{data[i, j]:.0%}" if persen else f"{int(data[i, j])}"
            ax.text(j, i, teks, ha="center", va="center",
                    color="white" if data[i, j] > batas else "black", fontsize=9)
    fig.tight_layout()
    return fig


def gambar_perbandingan(df):
    fig, ax = plt.subplots(figsize=(8, 4))
    x = np.arange(len(df))
    lebar = 0.2
    for k, m in enumerate(METRIK):
        batang = ax.bar(x + (k - 1.5) * lebar, df[m] * 100, lebar, label=m.replace("_", " "))
        ax.bar_label(batang, fmt="%.0f", fontsize=7, padding=1)
    ax.set_xticks(x)
    ax.set_xticklabels(df["Model"])
    ax.set_ylabel("Skor (%)")
    ax.set_ylim(0, 100)
    ax.legend(ncol=4, fontsize=8, loc="upper right")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


def kesalahan_terbesar(cm, kelas, top=3):
    cm = np.array(cm)
    pasangan = [(kelas[i], kelas[j], int(cm[i, j]), int(cm[i].sum()))
                for i in range(len(kelas)) for j in range(len(kelas))
                if i != j and cm[i, j] > 0]
    return sorted(pasangan, key=lambda p: p[2], reverse=True)[:top]


# =====================================================================
# SIDEBAR
# =====================================================================
with st.sidebar:
    st.header("🛰️ Tentang Aplikasi")
    st.write(
        "Klasifikasi tutupan lahan Jawa Timur dari citra **Sentinel-2** "
        "memakai tiga algoritma: Random Forest, Naive Bayes, dan Decision Tree."
    )
    st.markdown("**Legenda kelas**")
    for k in kelas_list:
        st.markdown(
            f"<span style='display:inline-block;width:14px;height:14px;"
            f"background:{warna[k]};border:1px solid #888;border-radius:3px;"
            f"margin-right:8px;vertical-align:middle'></span>{k}",
            unsafe_allow_html=True,
        )
    st.divider()
    st.caption(
        "Data: Sentinel-2 L2A via openEO (Copernicus) · komposit median · "
        "resolusi 100 m · proyeksi UTM 49S."
    )

# =====================================================================
# HEADER
# =====================================================================
st.title("Klasifikasi Tutupan Lahan Jawa Timur")
st.caption("Citra Sentinel-2 · Random Forest · Naive Bayes · Decision Tree")

tab_ringkas, tab_data, tab_eval, tab_peta, tab_prediksi, tab_catatan = st.tabs([
    "🏠 Ringkasan", "📡 Data & Fitur", "📊 Evaluasi Model",
    "🗺️ Peta Klasifikasi", "🔮 Prediksi", "⚠️ Catatan",
])

# =====================================================================
# TAB 1 — RINGKASAN
# =====================================================================
with tab_ringkas:
    st.subheader("Gambaran Umum")
    st.write(
        "Proyek ini memetakan enam kelas tutupan lahan di Jawa Timur: "
        "**Bangunan, Danau, Lahan Hijau, Laut, Mangrove, dan Sawah**. "
        "Sampel berupa poligon yang digambar manual, nilai spektralnya diambil dari "
        "citra Sentinel-2, lalu dipakai melatih dan membandingkan tiga algoritma "
        "klasifikasi. Model terbaik dipakai untuk memetakan seluruh area."
    )

    n_total = len(dataset) if dataset is not None else None
    n_uji = int(np.array(cm_data[NAMA_MODEL[0]]).sum()) if cm_data and NAMA_MODEL[0] in cm_data else None
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sampel valid", n_total if n_total else "—")
    c2.metric("Jumlah kelas", len(kelas_list))
    c3.metric("Data latih", (n_total - n_uji) if (n_total and n_uji) else "—")
    c4.metric("Data uji", n_uji if n_uji else "—")

    if hasil is not None:
        terbaik = hasil.iloc[0]
        st.success(
            f"**Model terbaik: {terbaik['Model']}** — F1-score macro "
            f"{terbaik['F1_macro']:.2%}, akurasi {terbaik['Akurasi']:.2%}. "
            "Model dipilih berdasarkan F1 macro karena menghitung semua kelas dengan bobot sama."
        )

    st.subheader("Alur Kerja")
    st.markdown(
        """
1. **Sampel**: 6 kelas × 75 poligon = 450 poligon (1 poligon tidak punya nilai band valid sehingga dibuang → 449).
2. **Pengambilan citra**: Sentinel-2 L2A lewat openEO, periode 9 Sep – 10 Okt 2026, awan maks. 10%, komposit median, resolusi 100 m.
3. **Ekstraksi fitur**: nilai B02, B03, B04, B08, B11 pada satu titik di dalam tiap poligon, ditambah NDVI dan NDWI → 7 fitur.
4. **Pembagian data**: 80% latih / 20% uji, *stratified*, `random_state=42`; ketiga model memakai pembagian yang sama.
5. **Pelatihan & evaluasi**: akurasi, precision, recall, F1, dan confusion matrix pada data uji.
6. **Pemetaan**: model terbaik memprediksi setiap piksel valid → peta klasifikasi (Matplotlib & Folium).
"""
    )

    if hasil is not None:
        st.subheader("Perbandingan Singkat")
        fmt = {m: "{:.2%}" for m in METRIK}
        tabel(hasil.style.format(fmt))
    else:
        st.warning("File `data/hasil_evaluasi.csv` tidak ditemukan.")

# =====================================================================
# TAB 2 — DATA & FITUR
# =====================================================================
with tab_data:
    st.subheader("Sumber Data: Sentinel-2")
    st.write(
        "Sentinel-2 adalah misi pengamatan bumi ESA (program Copernicus) dengan dua satelit "
        "yang mengamati lokasi yang sama setiap ±5 hari. Data yang dipakai adalah "
        "**Level-2A** (reflektansi permukaan yang sudah dikoreksi atmosfer). "
        "Beberapa citra digabung dengan **median temporal** agar awan dan bayangan berkurang."
    )
    tabel(INFO_BAND, hide_index=True)

    st.subheader("Indeks Spektral")
    ca, cb = st.columns(2)
    with ca:
        st.latex(r"NDVI=\frac{B08-B04}{B08+B04}")
        st.write("Mengukur kehijauan vegetasi. Nilai tinggi → vegetasi rapat; nilai rendah/negatif → bangunan, tanah terbuka, atau air.")
    with cb:
        st.latex(r"NDWI=\frac{B03-B08}{B03+B08}")
        st.write("Menonjolkan badan air. Nilai tinggi (positif) → air; vegetasi umumnya bernilai negatif.")

    if dataset is None:
        st.warning("File `data/dataset_sampel.csv` tidak ditemukan. Jalankan sel ekspor tambahan di notebook.")
    else:
        st.subheader("Sampel Pelatihan")
        k1, k2 = st.columns([1, 2])
        with k1:
            jumlah = dataset["Kelas"].value_counts().reindex(kelas_list).fillna(0).reset_index()
            jumlah.columns = ["Kelas", "Jumlah sampel"]
            tabel(jumlah, hide_index=True)
            st.caption("Rancangan awal 75 sampel per kelas; yang tampil adalah sampel dengan nilai band valid.")
        with k2:
            rata = dataset.groupby("Kelas")[FITUR].mean().reindex(kelas_list).round(3)
            st.markdown("**Rata-rata fitur per kelas**")
            tabel(rata)

        st.markdown("#### Tanda spektral rata-rata per kelas")
        panjang = (dataset.groupby("Kelas")[BAND].mean().reset_index()
                   .melt(id_vars="Kelas", var_name="Band", value_name="Reflektansi"))
        grafik = (
            alt.Chart(panjang)
            .mark_line(point=True)
            .encode(
                x=alt.X("Band:N", sort=BAND, title="Band (urut panjang gelombang)"),
                y=alt.Y("Reflektansi:Q", title="Reflektansi rata-rata (skala ×10.000)"),
                color=alt.Color("Kelas:N", scale=skala_warna()),
                tooltip=["Kelas", "Band", alt.Tooltip("Reflektansi:Q", format=".0f")],
            )
            .properties(height=360)
        )
        st.altair_chart(grafik)
        st.caption(
            "Kelas dengan kurva yang berimpit sulit dibedakan model. Perhatikan "
            "kurva vegetasi (naik tajam di B08) dibanding air (turun di B08 dan B11)."
        )

        st.markdown("#### Sebaran NDVI vs NDWI")
        sebar = (
            alt.Chart(dataset)
            .mark_circle(size=60, opacity=0.75, stroke="#555", strokeWidth=0.4)
            .encode(
                x=alt.X("NDVI:Q"), y=alt.Y("NDWI:Q"),
                color=alt.Color("Kelas:N", scale=skala_warna()),
                tooltip=["Kelas", alt.Tooltip("NDVI:Q", format=".3f"), alt.Tooltip("NDWI:Q", format=".3f")],
            )
            .properties(height=380)
            .interactive()
        )
        st.altair_chart(sebar)
        st.caption("Titik kelas yang saling bertumpuk menandakan fitur belum cukup memisahkan kelas tersebut.")

        with st.expander("Lihat & unduh dataset lengkap"):
            tabel(dataset)
            st.download_button(
                "⬇️ Unduh dataset (CSV)",
                dataset.to_csv(index=False).encode("utf-8"),
                file_name="dataset_sampel_6kelas.csv",
                mime="text/csv",
            )

# =====================================================================
# TAB 3 — EVALUASI MODEL
# =====================================================================
with tab_eval:
    st.subheader("Cara Menilai Model")
    st.write(
        "Setelah belajar dari data latih, model diuji pada **data uji** yang belum pernah "
        "dilihatnya. Lima ukuran yang dipakai:"
    )
    st.markdown(
        "- **Akurasi**: persentase tebakan benar secara keseluruhan.\n"
        "- **Precision**: dari semua yang ditebak sebagai suatu kelas, berapa persen yang benar.\n"
        "- **Recall**: dari semua sampel asli suatu kelas, berapa persen yang berhasil ditemukan.\n"
        "- **F1-score**: gabungan precision dan recall dalam satu angka.\n"
        "- **Confusion matrix**: tabel yang memperlihatkan kelas mana tertukar dengan kelas mana."
    )
    st.latex(r"\text{Precision}=\frac{TP}{TP+FP}\quad "
             r"\text{Recall}=\frac{TP}{TP+FN}\quad "
             r"F1=\frac{2\times \text{Precision}\times \text{Recall}}{\text{Precision}+\text{Recall}}")
    st.caption(
        "TP = tebakan benar, FP = salah menebak kelas ini, FN = sampel kelas ini yang terlewat. "
        "Versi *macro* adalah rata-rata semua kelas dengan bobot sama."
    )

    st.divider()
    st.subheader("Perbandingan Kinerja Model")
    if hasil is None:
        st.warning("File `data/hasil_evaluasi.csv` tidak ditemukan.")
    else:
        kolom_m = st.columns(len(hasil))
        for kol, (_, r) in zip(kolom_m, hasil.iterrows()):
            kol.metric(r["Model"], f"{r['F1_macro']:.1%}", help="F1-score macro")
            kol.caption(f"Akurasi {r['Akurasi']:.1%} · Precision {r['Precision_macro']:.1%} · Recall {r['Recall_macro']:.1%}")
        tabel(hasil.style.format({m: "{:.2%}" for m in METRIK}), hide_index=True)
        st.pyplot(gambar_perbandingan(hasil))

    st.divider()
    st.subheader("Penjelasan Algoritma")
    for nama in NAMA_MODEL:
        with st.expander(nama):
            st.write(PENJELASAN_MODEL[nama])

    st.divider()
    st.subheader("Confusion Matrix")
    st.caption(
        "Baris = kelas sebenarnya, kolom = tebakan model. Diagonal adalah tebakan benar; "
        "angka di luar diagonal adalah kesalahan. Versi persen sama dengan *recall* tiap kelas."
    )
    if cm_data is None:
        st.warning("File `data/confusion_matrix.json` tidak ditemukan. Jalankan sel ekspor tambahan di notebook.")
    else:
        pilihan = [n for n in NAMA_MODEL if n in cm_data]
        kiri, kanan = st.columns([1, 1])
        with kiri:
            model_cm = st.radio("Model", pilihan, horizontal=True, key="cm_model")
            mode_cm = st.radio("Tampilan", ["Jumlah sampel", "Persen per kelas"], horizontal=True, key="cm_mode")
            st.pyplot(gambar_cm(cm_data[model_cm], cm_data["kelas"], mode_cm == "Persen per kelas", model_cm))
        with kanan:
            st.markdown(f"**Kesalahan terbesar — {model_cm}**")
            for aktual, tebak, n, total in kesalahan_terbesar(cm_data[model_cm], cm_data["kelas"]):
                st.markdown(f"- **{aktual}** salah ditebak sebagai **{tebak}**: {n} dari {total} sampel")
            if laporan is not None:
                sub = laporan[laporan["Model"] == model_cm].set_index("Kelas")
                lemah = sub["F1"].idxmin()
                kuat = sub["F1"].idxmax()
                st.info(
                    f"Kelas paling mudah dikenali: **{kuat}** (F1 {sub.loc[kuat, 'F1']:.0%}). "
                    f"Paling sulit: **{lemah}** (F1 {sub.loc[lemah, 'F1']:.0%})."
                )

    if laporan is not None:
        st.divider()
        st.subheader("Kinerja per Kelas")
        pilih_metrik = st.radio("Metrik", ["F1", "Precision", "Recall"], horizontal=True, key="metrik_kelas")
        pivot = laporan.pivot(index="Kelas", columns="Model", values=pilih_metrik)
        pivot = pivot.reindex(index=kelas_list, columns=[n for n in NAMA_MODEL if n in pivot.columns])
        try:
            tabel(pivot.style.format("{:.0%}").background_gradient(cmap="Blues", vmin=0, vmax=1))
        except Exception:
            tabel(pivot.style.format("{:.0%}"))
        with st.expander("Classification report lengkap"):
            tabel(laporan.style.format({"Precision": "{:.2f}", "Recall": "{:.2f}", "F1": "{:.2f}"}), hide_index=True)

    st.divider()
    st.subheader("Fitur Paling Berpengaruh")
    ada_imp = [n for n in ("Random Forest", "Decision Tree") if n in models]
    if ada_imp:
        cols_imp = st.columns(len(ada_imp))
        for kol, nama in zip(cols_imp, ada_imp):
            m = models[nama]
            nama_fitur = list(getattr(m, "feature_names_in_", FITUR))
            imp = pd.Series(m.feature_importances_, index=nama_fitur).sort_values(ascending=False)
            with kol:
                st.markdown(f"**{nama}**")
                st.bar_chart(imp)
        st.caption("Naive Bayes tidak punya ukuran kepentingan fitur bawaan. Semakin tinggi batang, semakin sering fitur itu dipakai model untuk memisahkan kelas.")
    else:
        st.info("Model belum ditemukan di folder `models/`.")

# =====================================================================
# TAB 4 — PETA
# =====================================================================
with tab_peta:
    st.subheader("Peta Klasifikasi Tutupan Lahan")
    if meta is None or not (ASSETS / meta["file"][0]).exists():
        st.warning(
            "Aset peta belum tersedia (`data/peta_meta.json` dan `assets/layer_*.png`). "
            "Jalankan `ekspor_tambahan.py` sebagai sel terakhir di notebook, lalu salin folder "
            "`data/` dan `assets/` ke repositori."
        )
    else:
        st.write(
            f"Hasil prediksi **{meta.get('model_peta', 'model terbaik')}** pada setiap piksel valid "
            f"({meta['ukuran'][0]:,} × {meta['ukuran'][1]:,} piksel, resolusi {meta['resolusi_m']} m, "
            f"periode citra {meta['periode']}). Gunakan kontrol layer di pojok kanan atas peta."
        )

        c1, c2, c3 = st.columns([2, 1, 1])
        tampil = c1.multiselect("Kelas yang ditampilkan", kelas_list, default=kelas_list)
        opasitas = c2.slider("Opasitas layer", 0.1, 1.0, 0.6, 0.05)
        titik = c3.checkbox("Tampilkan titik sampel", value=False)

        @st.cache_resource(show_spinner="Menyusun peta...")
        def bangun_peta(kelas_tampil: tuple, opasitas: float, titik_sampel: bool):
            import folium

            (lat_min, lon_min), (lat_max, lon_max) = meta["bounds"]
            m = folium.Map(location=[(lat_min + lat_max) / 2, (lon_min + lon_max) / 2],
                           zoom_start=8, tiles=None)
            folium.TileLayer(
                tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                attr="Esri World Imagery", name="Peta Satelit Asli",
            ).add_to(m)
            folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)

            for kelas, berkas in zip(meta["kelas"], meta["file"]):
                folium.raster_layers.ImageOverlay(
                    image=str(ASSETS / berkas), bounds=meta["bounds"],
                    opacity=opasitas, name=f"Klasifikasi {kelas}",
                    show=kelas in kelas_tampil,
                ).add_to(m)

            if titik_sampel and dataset is not None:
                for kelas in meta["kelas"]:
                    grup = folium.FeatureGroup(name=f"Sampel {kelas}", show=kelas in kelas_tampil)
                    for _, r in dataset[dataset["Kelas"] == kelas].iterrows():
                        folium.CircleMarker(
                            location=[r["Latitude"], r["Longitude"]], radius=4,
                            color="black", weight=1, fill=True,
                            fill_color=warna.get(kelas, "#888"), fill_opacity=0.9,
                            tooltip=f"{kelas} · NDVI {r['NDVI']:.2f} · NDWI {r['NDWI']:.2f}",
                        ).add_to(grup)
                    grup.add_to(m)

            folium.LayerControl(position="topright", collapsed=False).add_to(m)
            return m

        peta_folium = bangun_peta(tuple(tampil), float(opasitas), bool(titik))
        try:
            from streamlit_folium import st_folium
            st_folium(peta_folium, height=620, use_container_width=True, returned_objects=[])
        except ImportError:
            import streamlit.components.v1 as components
            components.html(peta_folium._repr_html_(), height=640)

        st.markdown(
            " ".join(
                f"<span style='display:inline-block;width:12px;height:12px;background:{warna[k]};"
                f"border:1px solid #888;margin:0 4px 0 12px;vertical-align:middle'></span>{k}"
                for k in kelas_list
            ),
            unsafe_allow_html=True,
        )

        st.subheader("Luas per Kelas Hasil Prediksi")
        luas = pd.DataFrame({
            "Kelas": meta["kelas"],
            "Piksel": meta["piksel"],
            "Luas (km²)": meta["luas_km2"],
        })
        luas["Persentase"] = luas["Piksel"] / luas["Piksel"].sum()
        g1, g2 = st.columns([1, 1])
        with g1:
            tabel(luas.style.format({"Piksel": "{:,.0f}", "Luas (km²)": "{:,.1f}", "Persentase": "{:.1%}"}),
                  hide_index=True)
            st.caption(f"Total piksel valid: {meta['total_valid']:,}. Satu piksel ≈ {meta['resolusi_m']} m × {meta['resolusi_m']} m.")
        with g2:
            batang = (
                alt.Chart(luas).mark_bar()
                .encode(
                    x=alt.X("Kelas:N", sort=None), y=alt.Y("Luas (km²):Q"),
                    color=alt.Color("Kelas:N", scale=skala_warna(), legend=None),
                    tooltip=["Kelas", alt.Tooltip("Luas (km²):Q", format=",.1f"), alt.Tooltip("Persentase:Q", format=".1%")],
                )
                .properties(height=280)
            )
            st.altair_chart(batang)

        st.info(
            "Peta mencakup kotak batas (*bounding box*) seluruh sampel, bukan batas administrasi "
            "Provinsi Jawa Timur. Model hanya mengenal 6 kelas, jadi tutupan lain (hutan, lahan "
            "terbuka, dll.) dipaksa masuk ke salah satu kelas tersebut. Karena akurasi model "
            "±60%, luas di atas sebaiknya dibaca sebagai perkiraan kasar."
        )

# =====================================================================
# TAB 5 — PREDIKSI
# =====================================================================
with tab_prediksi:
    st.subheader("Prediksi Tutupan Lahan dari Nilai Band")
    if not models:
        st.error("Model tidak ditemukan di folder `models/`.")
    else:
        st.write(
            "Masukkan nilai reflektansi kelima band. **NDVI dan NDWI dihitung otomatis** dengan "
            "rumus yang sama seperti saat pelatihan. Gunakan skala **±0–10.000** "
            "(mis. B08 = 3473), bukan 0–1, sebab model dilatih dengan skala tersebut."
        )

        batas = dataset[BAND].agg(["min", "max"]) if dataset is not None else None
        awal = dataset[BAND].median() if dataset is not None else pd.Series(1500.0, index=BAND)
        for b in BAND:
            st.session_state.setdefault(f"in_{b}", float(awal[b]))

        def isi_contoh():
            kelas = st.session_state["contoh_kelas"]
            med = dataset.loc[dataset["Kelas"] == kelas, BAND].median()
            for b in BAND:
                st.session_state[f"in_{b}"] = float(med[b])

        kiri, kanan = st.columns([1, 1])
        with kiri:
            model_name = st.selectbox("Algoritma", list(models.keys()), key="model_prediksi")
            if dataset is not None:
                cc1, cc2 = st.columns([2, 1])
                cc1.selectbox("Isi dengan contoh (median sampel kelas)", kelas_list, key="contoh_kelas")
                cc2.write("")
                cc2.write("")
                cc2.button("Terapkan", on_click=isi_contoh)

            kb = st.columns(2)
            nilai = {}
            for i, b in enumerate(BAND):
                info = INFO_BAND.set_index("Band").loc[b, "Nama"]
                with kb[i % 2]:
                    nilai[b] = st.number_input(f"{b} · {info}", min_value=0.0, step=10.0,
                                               format="%.1f", key=f"in_{b}")

            ndvi = (nilai["B08"] - nilai["B04"]) / (nilai["B08"] + nilai["B04"] + 1e-6)
            ndwi = (nilai["B03"] - nilai["B08"]) / (nilai["B03"] + nilai["B08"] + 1e-6)
            m1, m2 = st.columns(2)
            m1.metric("NDVI (otomatis)", f"{ndvi:.3f}")
            m2.metric("NDWI (otomatis)", f"{ndwi:.3f}")

            if max(nilai.values()) < 50:
                st.warning("Semua nilai sangat kecil. Apakah ini skala 0–1? Model dilatih dengan skala ±0–10.000.")
            elif batas is not None:
                di_luar = [b for b in BAND if nilai[b] < batas.loc["min", b] * 0.5 or nilai[b] > batas.loc["max", b] * 1.5]
                if di_luar:
                    st.warning(f"Nilai {', '.join(di_luar)} jauh di luar rentang data latih; hasil prediksi kurang dapat diandalkan.")

            jalankan = st.button("🔮 Prediksi", type="primary")

        with kanan:
            if jalankan:
                x = pd.DataFrame([[*(nilai[b] for b in BAND), ndvi, ndwi]], columns=FITUR)
                model = models[model_name]
                pred = model.predict(x)[0]
                proba = pd.Series(model.predict_proba(x)[0], index=model.classes_)

                st.success(f"Hasil prediksi ({model_name}): **{pred}** — keyakinan {proba[pred]:.0%}")
                st.markdown("**Probabilitas tiap kelas**")
                dfp = proba.rename("Probabilitas").reset_index().rename(columns={"index": "Kelas"})
                dfp.columns = ["Kelas", "Probabilitas"]
                st.altair_chart(
                    alt.Chart(dfp).mark_bar().encode(
                        x=alt.X("Probabilitas:Q", scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format="%")),
                        y=alt.Y("Kelas:N", sort="-x"),
                        color=alt.Color("Kelas:N", scale=skala_warna(), legend=None),
                        tooltip=["Kelas", alt.Tooltip("Probabilitas:Q", format=".1%")],
                    ).properties(height=240)
                )

                st.markdown("**Perbandingan ketiga model pada masukan yang sama**")
                banding = []
                for nama, m in models.items():
                    p = m.predict(x)[0]
                    banding.append({"Model": nama, "Prediksi": p,
                                    "Keyakinan": float(pd.Series(m.predict_proba(x)[0], index=m.classes_)[p])})
                tabel(pd.DataFrame(banding).style.format({"Keyakinan": "{:.0%}"}), hide_index=True)
                st.caption(
                    "Keyakinan Naive Bayes sering terlalu ekstrem (mendekati 100%) walau akurasinya paling rendah; "
                    "jangan menganggapnya sebagai ukuran ketepatan."
                )
            else:
                st.info("Atur nilai band di sebelah kiri lalu tekan **Prediksi**.")

# =====================================================================
# TAB 6 — CATATAN
# =====================================================================
with tab_catatan:
    st.subheader("Keterbatasan & Cara Membaca Hasil")
    st.markdown(
        """
- **Satu poligon = satu piksel 100 m.** Poligon kecil dapat berisi campuran objek (*mixed pixel*), sehingga
  nilai spektralnya tidak murni. Contohnya, ada sampel *Bangunan* dengan NDVI sangat tinggi (±0,85) karena
  piksel tersebut didominasi vegetasi.
- **Jumlah data terbatas.** Hanya sekitar 449 sampel, dan data uji hanya ±15 sampel per kelas, sehingga
  satu sampel saja mengubah recall satu kelas sebesar ±7 poin. Selisih kecil antar model perlu dibaca hati-hati.
- **Kelas yang mirip secara spektral sering tertukar**, misalnya *Sawah* dengan *Lahan Hijau*, serta *Danau*
  dengan kelas lain. Laut dan Mangrove relatif mudah dikenali.
- **Satu waktu pengamatan.** Citra adalah komposit satu periode (9 Sep – 10 Okt 2026); sawah dan vegetasi
  berubah menurut musim tanam.
- **Cakupan peta** mengikuti kotak batas sampel dan hanya 6 kelas, sehingga tutupan lain dipaksa masuk
  ke kelas terdekat.
- **Model belum disetel.** Random Forest memakai 100 pohon, Decision Tree tanpa batas kedalaman, dan tidak ada
  validasi silang. Penyetelan hiperparameter serta penambahan fitur (misalnya tekstur, indeks lain, atau data multi-waktu)
  berpeluang menaikkan akurasi.
"""
    )
    st.subheader("Berkas yang Dibutuhkan Aplikasi")
    st.code(
        "models/random_forest.joblib, naive_bayes.joblib, decision_tree.joblib\n"
        "data/hasil_evaluasi.csv, dataset_sampel.csv, laporan_klasifikasi.csv,\n"
        "     confusion_matrix.json, peta_meta.json\n"
        "assets/layer_0.png ... layer_5.png",
        language="text",
    )