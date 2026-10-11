import json

cells = []
def _id(): return f"cell-{len(cells):02d}"
def md(s): cells.append({"cell_type": "markdown", "id": _id(), "metadata": {}, "source": s.strip("\n").splitlines(True)})
def code(s): cells.append({"cell_type": "code", "id": _id(), "execution_count": None, "metadata": {}, "outputs": [], "source": s.strip("\n").splitlines(True)})

md("""
# Klasifikasi Spasial Tutupan Lahan (6 Kelas) Menggunakan Citra Sentinel-2A

Bagian ini mendokumentasikan tahapan ekstraksi nilai spektral dari 450 titik sampel secara langsung menggunakan `aggregate_spatial` via **Copernicus Data Space (openEO)**, tanpa harus mengunduh file `.tif` berskala provinsi yang dapat membuat RAM crash.

Selanjutnya, model Random Forest dilatih menggunakan hasil ekstraksi tersebut, dan diterapkan pada area citra berskala kecil untuk visualisasi Peta Klasifikasi menggunakan **Folium**.
""")

md("""
## Instalasi Library Yang Digunakan
""")
code("""
pip install geopandas openeo scikit-learn seaborn matplotlib folium rasterio
""")

md("""
## 1. Desain Pengambilan Sampel (Ground Truth)

Pengambilan sampel dilakukan secara spasial ke dalam 6 kelas dalam format vektor (`Shapefile`).
Untuk mengekstrak fitur seluruh sampel (450 poligon), kita mengekspor sampel ini ke dalam format GeoJSON.
""")
code("""
import os, zipfile, warnings
import geopandas as gpd
import openeo
import pandas as pd

warnings.filterwarnings('ignore')

kelas_list = ['bangunan', 'danau', 'lahanHijau', 'laut', 'mangrove', 'sawah']
gdf_list = []

if not os.path.exists('land') and os.path.exists(os.path.join('data', 'land')):
    os.chdir('data')

for idx, nama in enumerate(kelas_list):
    zip_path = os.path.join('land', f'{nama}.zip')
    extract_path = os.path.join('land', f'sampel_{nama}')
    
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(extract_path)
    
    shp_file = None
    for root, dirs, files in os.walk(extract_path):
        for f in files:
            if f.endswith('.shp'):
                shp_file = os.path.join(root, f)
                break
        if shp_file:
            break
            
    if shp_file:
        gdf_temp = gpd.read_file(shp_file).to_crs("EPSG:4326")
        gdf_temp['label_teks'] = nama
        gdf_temp['label'] = idx
        gdf_list.append(gdf_temp[['label_teks', 'label', 'geometry']])

gdf_gabungan = gpd.GeoDataFrame(pd.concat(gdf_list, ignore_index=True), crs="EPSG:4326")

for nama in kelas_list:
    print(f"Jumlah sampel {nama} : {(gdf_gabungan['label_teks'] == nama).sum()}")

print(f"Total sampel gabungan   : {len(gdf_gabungan)}")

# Simpan sampel ke geojson untuk openEO
file_geojson = "samples_450.geojson"
gdf_gabungan.to_file(file_geojson, driver="GeoJSON")
print(f"File {file_geojson} berhasil dibuat untuk ekstraksi via OpenEO.")
""")

md("""
## 2. Ekstraksi Fitur Langsung via OpenEO (`aggregate_spatial`)

Kita menggunakan `aggregate_spatial` pada objek `datacube` untuk mengambil fitur 5 Band secara langsung dari server openEO berdasarkan letak poligon di `samples_450.geojson`.
Langkah ini digunakan sebagai ganti `.download()` untuk mengakali batas ukuran piksel maksimal OpenEO (20.000 x 20.000 piksel).
""")
code("""
import json
import numpy as np

minx, miny, maxx, maxy = gdf_gabungan.total_bounds
buffer_deg = 0.005

bbox = {
    "west": float(minx - buffer_deg),
    "south": float(miny - buffer_deg),
    "east": float(maxx + buffer_deg),
    "north": float(maxy + buffer_deg),
}
print("Bounding Box Gabungan:", bbox)

conn = openeo.connect("openeo.dataspace.copernicus.eu")
conn.authenticate_oidc()

datacube = conn.load_collection(
    "SENTINEL2_L2A",
    spatial_extent=bbox,
    temporal_extent=["2026-05-01", "2026-09-30"],
    bands=["B02", "B03", "B04", "B08", "B11"],
    max_cloud_cover=10,
)

composite_s2 = datacube.median_time()

json_file = "aggregated_features.json"
if not os.path.exists(json_file):
    print("Mengekstrak nilai band menggunakan aggregate_spatial (mungkin memakan waktu bbrp menit)...")
    ts = composite_s2.aggregate_spatial(geometries="samples_450.geojson", reducer="mean")
    ts.download(json_file, format="JSON")
    print(f"Berhasil diekstrak: {json_file}")
else:
    print(f"File {json_file} sudah ada, melewati proses ekstraksi.")
""")

md("""
## 3. Pembuatan Dataset dan Hasil Evaluasi Klasifikasi 6 Kelas (Random Forest)

Kita mem-parsing file JSON hasil OpenEO ke dalam DataFrame. Evaluasi menggunakan algoritma Random Forest dengan *Stratified Train-Test Split* (80% Data Latih, 20% Data Uji).
""")
code("""
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split

with open(json_file, "r") as f:
    data_json = json.load(f)

# Parsing struktur JSON hasil openEO aggregate_spatial
# Format yang dikembalikan openEO adalah list 2D: [[B02, B03, B04, B08, B11], ...]
rows = []
for idx_int, bands in enumerate(data_json):
    if bands is None or len(bands) == 0:
        bands = [np.nan] * 5
    rows.append([idx_int] + list(bands))

columns = ["poly_idx", "B02", "B03", "B04", "B08", "B11"]
df_features = pd.DataFrame(rows, columns=columns)
df_features = df_features.sort_values("poly_idx").reset_index(drop=True)

df_dataset = pd.concat([gdf_gabungan, df_features[["B02", "B03", "B04", "B08", "B11"]]], axis=1)

df_dataset["NDVI"] = (df_dataset["B08"] - df_dataset["B04"]) / (
    df_dataset["B08"] + df_dataset["B04"] + 1e-6
)
df_dataset["NDWI"] = (df_dataset["B03"] - df_dataset["B08"]) / (
    df_dataset["B03"] + df_dataset["B08"] + 1e-6
)

df_dataset.dropna(subset=["B02"], inplace=True)

df_dataset["Longitude"] = df_dataset.geometry.centroid.x
df_dataset["Latitude"] = df_dataset.geometry.centroid.y
df_dataset["Kelas"] = df_dataset["label_teks"]
df_dataset["Target"] = df_dataset["label"]

df_dataset.to_csv("dataset_sampel_6kelas.csv", index=False)
print("Dataset berhasil disimpan ke 'dataset_sampel_6kelas.csv'")
display(df_dataset.head())

fitur_kolom = ["B02", "B03", "B04", "B08", "B11", "NDVI", "NDWI"]
X = df_dataset[fitur_kolom]
y = df_dataset["Kelas"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

model_rf = RandomForestClassifier(n_estimators=100, random_state=42)
model_rf.fit(X_train, y_train)

y_pred = model_rf.predict(X_test)
print("\\n=== HASIL EVALUASI KLASIFIKASI 6 KELAS ===")
print(f"Akurasi Testing : {accuracy_score(y_test, y_pred) * 100:.2f}%")
print("\\nConfusion Matrix:\\n", confusion_matrix(y_test, y_pred))
print("\\nClassification Report:\\n", classification_report(y_test, y_pred))
""")

md("""
## 4. Visualisasi Peta Klasifikasi (Seluruh Provinsi Jawa Timur via Batch Job)

Sesuai kebutuhan, Peta Klasifikasi ini dieksekusi secara utuh mencakup 1 provinsi penuh. Karena batasan dari OpenEO yang melarang proses sinkron pada area seluas ini, kita menggunakan fitur **OpenEO Batch Job** yang akan dieksekusi dalam antrean (membutuhkan waktu tunggu). Resolusi juga diturunkan ke 100m (`resample_spatial`) secara internal agar hasil unduhan `.tif` tidak berukuran Gigabyte yang dapat membuat RAM/Memori Anda *crash*.
""")

code("""
import os
import rasterio
from matplotlib.colors import ListedColormap
import matplotlib.pyplot as plt
import folium
from rasterio.warp import transform_bounds
import numpy as np

# Bounding box Jatim secara utuh
bbox_vis = {
    "west": float(minx - buffer_deg),
    "south": float(miny - buffer_deg),
    "east": float(maxx + buffer_deg),
    "north": float(maxy + buffer_deg),
}

datacube_vis = conn.load_collection(
    "SENTINEL2_L2A",
    spatial_extent=bbox_vis,
    temporal_extent=["2026-05-01", "2026-09-30"],
    bands=["B02", "B03", "B04", "B08", "B11"],
    max_cloud_cover=10,
)

composite_vis = datacube_vis.median_time()

# Menurunkan resolusi ke 100m di Batch Job agar memori laptop tidak crash (Area tetap seluruh Jatim)
composite_vis = composite_vis.resample_spatial(resolution=100, projection=32749)

nama_tif_vis = "sentinel2_6kelas_visual_full.tif"
if not os.path.exists(nama_tif_vis):
    print("Mengunduh Peta Visualisasi Jatim menggunakan OpenEO Batch Job...")
    print("MOHON BERSABAR. Proses ini akan masuk ke sistem antrean OpenEO dan mungkin memakan waktu 15 - 30 menit.")
    job = composite_vis.create_job(out_format="GTiff", title="Full_Jatim_100m")
    job.start_and_wait()
    
    # Unduh hasil batch job
    job.download_results(".")
    
    # Cari file .tif dari batch job lalu rename
    for f in os.listdir("."):
        if f.endswith(".tif") and f != nama_tif_vis and "sentinel2" not in f:
            os.rename(f, nama_tif_vis)
            break
            
    print(f"Berhasil diunduh: {nama_tif_vis}")
else:
    print(f"File {nama_tif_vis} sudah ada, melewati proses Batch Job.")

with rasterio.open(nama_tif_vis) as src:
    img = src.read()
    ext = [src.bounds.left, src.bounds.right, src.bounds.bottom, src.bounds.top]
    lon_min, lat_min, lon_max, lat_max = transform_bounds(src.crs, 'EPSG:4326', *src.bounds)

b02 = img[0].astype(np.float32)
b03 = img[1].astype(np.float32)
b04 = img[2].astype(np.float32)
b08 = img[3].astype(np.float32)
b11 = img[4].astype(np.float32)

ndvi = (b08 - b04) / (b08 + b04 + 1e-6)
ndwi = (b03 - b08) / (b03 + b08 + 1e-6)

fitur_piksel = np.stack([b02, b03, b04, b08, b11, ndvi, ndwi], axis=-1)

h, w, n = fitur_piksel.shape
flat = fitur_piksel.reshape(-1, n)

# Pastikan exclude NoData
valid = np.isfinite(flat).all(axis=1) & np.all(flat[:, :5] != -32768, axis=1) & np.all(flat[:, :5] > 0, axis=1)
peta = np.full(h * w, np.nan)

if valid.any():
    preds = model_rf.predict(flat[valid])
    class_mapping = {cls: float(idx) for idx, cls in enumerate(kelas_list)}
    preds_int = np.array([class_mapping[p] for p in preds])
    peta[valid] = preds_int

peta = peta.reshape(h, w)

# Plot hasil dengan matlplotlib
fig, ax = plt.subplots(figsize=(10, 6))
cmap_colors = ['red', 'blue', 'lime', 'cyan', 'purple', 'yellow']
im = ax.imshow(peta, cmap=ListedColormap(cmap_colors), vmin=0, vmax=5, extent=ext)
cbar = plt.colorbar(im, ax=ax, ticks=[0.4, 1.25, 2.1, 2.9, 3.75, 4.6], shrink=0.7)
cbar.ax.set_yticklabels(kelas_list)
ax.set_title('Peta Klasifikasi 6 Kelas (Seluruh Provinsi Jawa Timur)')
plt.show()
""")

code("""
folium_bounds = [[lat_min, lon_min], [lat_max, lon_max]]
center_lat = (lat_min + lat_max) / 2
center_lon = (lon_min + lon_max) / 2

m = folium.Map(location=[center_lat, center_lon], zoom_start=8)

folium.TileLayer(
    tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attr='Esri World Imagery',
    name='Peta Satelit Asli',
    overlay=False
).add_to(m)

rgba_colors = [
    [255, 0, 0, 255],     # bangunan: red
    [0, 0, 255, 255],     # danau: blue
    [0, 255, 0, 255],     # lahanHijau: lime
    [0, 255, 255, 255],   # laut: cyan
    [128, 0, 128, 255],   # mangrove: purple
    [255, 255, 0, 255]    # sawah: yellow
]

for idx, cls in enumerate(kelas_list):
    cls_img = np.zeros((h, w, 4), dtype=np.uint8)
    cls_img[peta == float(idx)] = rgba_colors[idx]
    
    folium.raster_layers.ImageOverlay(
        image=cls_img,
        bounds=folium_bounds,
        opacity=0.6,          
        name=f'Klasifikasi {cls}'
    ).add_to(m)

folium.LayerControl(position='topright').add_to(m)

m
""")

nb = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
with open('d:/KULIAH/MATKUL/PSD/PSD/data/klasifikasiJatim.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)

print("Notebook klasifikasiJatim.ipynb berhasil dibuat.")
