import json

with open('data/clusterBaik.ipynb', 'r', encoding='utf-8') as f:
    nb = json.load(f)

markdown_hasil = """## 5. Hasil Eksperimen KNIME

Berdasarkan eksperimen di KNIME, hasil *Silhouette Coefficient* untuk ketiga percobaan dimensi PCA (**203, 74, dan 37**) ternyata memberikan **hasil yang sama persis** untuk setiap nilai $k$. 

**Mengapa hasilnya sama?**
Karena jumlah baris data (responden) kita hanya ada **37 baris**. Dalam algoritma PCA, jumlah maksimum *principal components* (komponen utama) yang bisa diekstrak tidak akan melebihi jumlah baris data. 
Jadi, walaupun kita menyetel parameter PCA menjadi 203 atau 74, sistem secara otomatis hanya bisa mengekstrak maksimal 37 fitur. Akibatnya, data hasil PCA 203, PCA 74, dan PCA 37 adalah data yang **sama persis**. Karena datanya sama, hasil pengelompokan k-Means dan skor Silhouette-nya pun menjadi identik.

Berikut adalah hasil *Silhouette Coefficient* untuk percobaan $k=2, 3, 5$:

### Data Linier

| Jumlah Cluster (k) | Skor Cluster | Overall Silhouette |
| :--- | :--- | :--- |
| **k = 2** | cluster_0: 0.8783<br>cluster_1: 0.3567 | **0.8219** |
| **k = 3** | cluster_1: 0.7873<br>cluster_0: 0.2702<br>cluster_2: 0.1345 | **0.6468** |
| **k = 5** | cluster_2: 0.6850<br>cluster_1: 0.4198<br>cluster_0: 0.5710<br>cluster_4: 0.9706<br>cluster_3: 0.4269 | **0.6373** |

### Data Polynomial

| Jumlah Cluster (k) | Skor Cluster | Overall Silhouette |
| :--- | :--- | :--- |
| **k = 2** | cluster_0: 0.6923<br>cluster_1: 0.3345 | **0.6343** |
| **k = 3** | cluster_2: 0.5828<br>cluster_0: 0.1939<br>cluster_1: 0.4027 | **0.4711** |
| **k = 5** | cluster_3: 0.5526<br>cluster_0: 0.3960<br>cluster_4: 0.5814<br>cluster_2: 0.1729<br>cluster_1: 0.6772 | **0.4856** |

**Kesimpulan:**
Cluster terbaik diperoleh saat **k = 2** untuk kedua dataset, karena menghasilkan nilai rata-rata (*Overall*) Silhouette tertinggi, yaitu **0.8219** (Data Linier) dan **0.6343** (Data Polynomial).
"""

# Update the specific markdown cell
for i, cell in enumerate(nb['cells']):
    if cell['cell_type'] == 'markdown' and '## 5. Hasil Eksperimen KNIME' in ''.join(cell['source']):
        nb['cells'][i]['source'] = markdown_hasil.splitlines(True)
        break

# Adding map code if it doesn't exist
has_map_code = False
for cell in nb['cells']:
    if cell['cell_type'] == 'code' and 'folium.Map' in ''.join(cell['source']):
        has_map_code = True
        break

if not has_map_code:
    # Update the header for the map
    for i, cell in enumerate(nb['cells']):
        if cell['cell_type'] == 'markdown' and '## 6. Peta Hasil Cluster' in ''.join(cell['source']):
            nb['cells'][i]['source'] = [
                '## 6. Peta Hasil Cluster\n',
                '\n',
                'Karena **k = 2** adalah yang terbaik (baik untuk data linier maupun polynomial), mari kita tampilkan hasil clustering tersebut di atas peta.\n',
                'Kita akan melakukan PCA menjadi 37 komponen, mengelompokkannya menjadi 2 cluster dengan k-Means, dan menampilkannya di peta Folium.'
            ]
            break
            
    map_code = """import folium

# Kita gunakan data linier sebagai contoh terbaik (Silhouette tertinggi 0.8219)
df_map = pd.read_csv('data_linier.csv')

# Ambil fitur numerik dan lakukan PCA & k-Means (k=2)
X_map = StandardScaler().fit_transform(fitur_numerik(df_map))
Z_map = PCA(n_components=min(37, X_map.shape[0]), random_state=42).fit_transform(X_map)
df_map['Cluster'] = KMeans(n_clusters=2, n_init=10, random_state=42).fit_predict(Z_map)

# Data koordinat lokasi daerah (Dukun, Gresik)
# Karena CSV awal tidak memiliki kolom latitude dan longitude, kita tambahkan dummy koordinat untuk visualisasi 
# (Silakan ganti dengan koordinat sebenarnya jika ada)
# Untuk contoh, kita buat sebaran koordinat acak di sekitar wilayah Gresik (-7.15, 112.65)
np.random.seed(42)
df_map['latitude'] = -7.15 + np.random.normal(0, 0.05, len(df_map))
df_map['longitude'] = 112.65 + np.random.normal(0, 0.05, len(df_map))

# Inisialisasi peta
peta = folium.Map(location=[-7.15, 112.65], zoom_start=11)
warna_cluster = {0: 'red', 1: 'blue'}

# Tambahkan marker untuk setiap daerah
for idx, row in df_map.iterrows():
    folium.CircleMarker(
        location=[row['latitude'], row['longitude']],
        radius=8,
        popup=f"Daerah: {row['daerah']}<br>Nama: {row['nama']}<br>Cluster: {row['Cluster']}",
        color=warna_cluster[row['Cluster']],
        fill=True,
        fill_color=warna_cluster[row['Cluster']],
        fill_opacity=0.7
    ).add_to(peta)

# Tampilkan peta
peta"""
    nb['cells'].append({
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": map_code.splitlines(True)
    })

with open('data/clusterBaik.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)
