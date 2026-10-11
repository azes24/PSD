
import streamlit as st
import pandas as pd
import joblib

st.set_page_config(
    page_title="Klasifikasi Tutupan Lahan Jawa Timur",
    page_icon="🛰️",
    layout="wide"
)

st.title("Klasifikasi Tutupan Lahan Jawa Timur")
st.write(
    "Klasifikasi berbasis citra Sentinel-2 "
    "menggunakan Random Forest, Naive Bayes, dan Decision Tree."
)

@st.cache_resource
def load_models():
    return {
        "Random Forest": joblib.load(
            "models/random_forest.joblib"
        ),
        "Naive Bayes": joblib.load(
            "models/naive_bayes.joblib"
        ),
        "Decision Tree": joblib.load(
            "models/decision_tree.joblib"
        )
    }

@st.cache_data
def load_evaluation():
    return pd.read_csv("data/hasil_evaluasi.csv")

models = load_models()
hasil = load_evaluation()

tab1, tab2 = st.tabs([
    "Evaluasi Model",
    "Prediksi Kelas"
])

with tab1:
    st.subheader("Perbandingan Kinerja Model")
    st.dataframe(hasil, use_container_width=True)

    if "Akurasi" in hasil.columns:
        st.bar_chart(
            hasil.set_index("Model")[["Akurasi", "F1_macro"]]
        )

with tab2:
    st.subheader("Prediksi Tutupan Lahan")

    model_name = st.selectbox(
        "Pilih algoritma",
        list(models.keys())
    )

    fitur = ["B02", "B03", "B04", "B08",
             "B11", "NDVI", "NDWI"]

    with st.form("form_prediksi"):
        nilai = []
        kolom = st.columns(2)

        for i, nama in enumerate(fitur):
            with kolom[i % 2]:
                nilai.append(
                    st.number_input(
                        nama,
                        value=0.1,
                        format="%.6f"
                    )
                )

        submit = st.form_submit_button("Prediksi")

    if submit:
        X_input = pd.DataFrame([nilai], columns=fitur)
        prediksi = models[model_name].predict(X_input)[0]

        st.success(f"Hasil prediksi: {prediksi}")
