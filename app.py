from flask import Flask, render_template, request
import heapq
import googlemaps
import polyline
import time

API_KEY = "AIzaSyA4S8g1DTPD-bAASccIWJ1uaAypHru5BBM"
gmaps = googlemaps.Client(key=API_KEY)

app = Flask(__name__)

# ==============================
# CAPITALES
# ==============================
capitales = {
    "Puno": (-15.84, -70.02),
    "Amazonas": (-6.23, -77.87),
    "Ancash": (-9.53, -77.53),
    "Apurimac": (-13.63, -72.88),
    "Arequipa": (-16.40, -71.53),
    "Ayacucho": (-13.16, -74.22),
    "Cajamarca": (-7.16, -78.50),
    "Callao": (-12.05, -77.14),
    "Cusco": (-13.52, -71.97),
    "Huancavelica": (-12.78, -74.97),
    "Huanuco": (-9.93, -76.24),
    "Ica": (-14.06, -75.73),
    "Junin": (-12.07, -75.20),
    "La Libertad": (-8.11, -79.02),
    "Lambayeque": (-6.77, -79.84),
    "Lima": (-12.04, -77.03),
    "Loreto": (-3.75, -73.25),
    "Madre de Dios": (-12.59, -69.18),
    "Moquegua": (-17.19, -70.94),
    "Pasco": (-10.68, -76.26),
    "Piura": (-5.19, -80.63),
    "San Martin": (-6.03, -76.97),
    "Tacna": (-18.01, -70.25),
    "Tumbes": (-3.57, -80.45),
    "Ucayali": (-8.38, -74.55)
}

# ==============================
# CACHE
# ==============================
cache = {}

def obtener_ruta_real(origen, destino):
    clave = tuple(sorted((origen, destino)))

    if clave in cache:
        return cache[clave]

    try:
        directions = gmaps.directions(
            origen + ", Peru",
            destino + ", Peru",
            mode="driving"
        )

        if not directions:
            return (9999, 9999, [])

        ruta = directions[0]

        distancia = ruta['legs'][0]['distance']['value'] / 1000
        tiempo = ruta['legs'][0]['duration']['value'] / 3600
        puntos = polyline.decode(ruta['overview_polyline']['points'])

        cache[clave] = (distancia, tiempo, puntos)
        return distancia, tiempo, puntos

    except Exception as e:
        print("Error:", e)
        return (9999, 9999, [])

# ==============================
# GRAFO (SIN CARGAR TODO AL INICIO)
# ==============================
grafo = {dep: [] for dep in capitales}

conexiones = [
    # COSTA NORTE
    ("Tumbes","Piura"),
    ("Piura","Lambayeque"),
    ("Lambayeque","La Libertad"),
    ("La Libertad","Ancash"),
    ("Ancash","Lima"),

    # COSTA SUR
    ("Lima","Ica"),
    ("Ica","Arequipa"),
    ("Arequipa","Moquegua"),
    ("Moquegua","Tacna"),

    # SIERRA CENTRAL
    ("Lima","Junin"),
    ("Junin","Pasco"),
    ("Pasco","Huanuco"),

    # SELVA
    ("Huanuco","Ucayali"),
    ("Ucayali","Loreto"),
    ("Loreto","San Martin"),
    ("San Martin","Amazonas"),

    # NORTE INTERIOR
    ("Amazonas","Cajamarca"),
    ("Cajamarca","La Libertad"),

    # CENTRO SUR
    ("Junin","Huancavelica"),
    ("Huancavelica","Ayacucho"),
    ("Ayacucho","Apurimac"),
    ("Apurimac","Cusco"),

    # SUR
    ("Cusco","Puno"),
    ("Cusco","Arequipa"),
    ("Arequipa","Puno"),
    ("Puno","Tacna"),

    # EXTRA IMPORTANTES 🔥
    ("Lima","Huanuco"),
    ("Lima","Ayacucho"),
    ("Arequipa","Ayacucho"),
    ("Cusco","Junin"),
    ("Huanuco","San Martin"),
    ("Cajamarca","Piura"),
    ("Ancash","Huanuco"),
    ("Ucayali","Madre de Dios"),
    ("Cusco","Madre de Dios"),
]

def construir_grafo():
    for a, b in conexiones:
        distancia, tiempo, puntos = obtener_ruta_real(a, b)

        grafo[a].append((b, distancia, tiempo, puntos))
        grafo[b].append((a, distancia, tiempo, list(reversed(puntos))))

        time.sleep(0.1)  # evita saturar API

# ==============================
# DIJKSTRA
# ==============================
def dijkstra(grafo, inicio, fin):
    cola = [(0, inicio)]
    distancias = {n: float('inf') for n in grafo}
    distancias[inicio] = 0
    previos = {n: None for n in grafo}

    pasos = []

    while cola:
        dist_actual, nodo_actual = heapq.heappop(cola)

        pasos.append(f"Visitando {nodo_actual} ({round(dist_actual,2)} km)")

        if nodo_actual == fin:
            break

        for vecino, peso, tiempo, puntos in grafo[nodo_actual]:
            nueva = dist_actual + peso

            if nueva < distancias[vecino]:
                distancias[vecino] = nueva
                previos[vecino] = nodo_actual
                heapq.heappush(cola, (nueva, vecino))

                pasos.append(f"{vecino} actualizado desde {nodo_actual} → {round(nueva,2)} km")

    if distancias[fin] == float('inf'):
        return ["No hay ruta"], 0, pasos

    ruta = []
    nodo = fin
    while nodo:
        ruta.insert(0, nodo)
        nodo = previos[nodo]

    return ruta, round(distancias[fin], 2), pasos

# ==============================
# TRAMOS
# ==============================
def obtener_tramos(ruta):
    tramos = []

    for i in range(len(ruta) - 1):
        origen = ruta[i]
        destino = ruta[i + 1]

        for vecino, peso, tiempo, puntos in grafo[origen]:
            if vecino == destino:
                tramos.append({
                    "origen": origen,
                    "destino": destino,
                    "distancia": round(peso, 2),
                    "tiempo": round(tiempo, 2),
                    "coords": puntos
                })
                break

    return tramos

# ==============================
# FLASK
# ==============================
@app.route("/", methods=["GET", "POST"])
def index():
    ruta = []
    distancia_total = 0
    tramos = []
    pasos = []
    coords = []

    if request.method == "POST":

        # 🔥 construir grafo SOLO cuando se usa
        if not grafo["Lima"]:  
            construir_grafo()

        origen = request.form["origen"]
        destino = request.form["destino"]

        if origen == destino:
            ruta = [origen]
        else:
            ruta, distancia_total, pasos = dijkstra(grafo, origen, destino)

        if ruta != ["No hay ruta"]:
            tramos = obtener_tramos(ruta)
            for tramo in tramos:
                coords.extend(tramo["coords"])

            if origen == destino:
                coords = [capitales[origen]]

    return render_template(
        "index.html",
        departamentos=capitales.keys(),
        ruta=ruta,
        distancia=distancia_total,
        tramos=tramos,
        pasos=pasos,
        coords=coords
    )

if __name__ == "__main__":
    app.run(debug=True)