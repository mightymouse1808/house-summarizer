# Resumidor de casas
Open source webpage meant to help keep track of house-search-related information 

Contenido de la carpeta:

| Archivo | Para qué sirve |
|---|---|
| `index.html` | La página (tarjetas con foto, dirección, precio, etc.) |
| `data.json` | Los datos de las casas. La página lee y escribe aquí |
| `parse.py` | Script que lee los links de Zillow/Redfin/Realtor/Move with Momentum y llena `data.json` |
| `requirements.txt` | Librerías de Python que necesita `parse.py` |

## 1. Subir a GitHub y activar la página

1. Crea una cuenta en https://github.com si no tienes.
2. Arriba a la derecha: **+ → New repository**. Nombre: `casas`. Ponlo **Public** (Pages gratis lo requiere en cuentas gratis). Crear.
3. En el repo: **Add file → Upload files**. Arrastra `index.html`, `data.json`, `parse.py`, `requirements.txt` y `README.md`. Abajo: **Commit changes**.
4. **Settings → Pages**. En "Branch" elige `main` y carpeta `/ (root)`. **Save**.
5. Espera 1 o 2 minutos. Tu página queda en `https://TUUSUARIO.github.io/casas/`.

Ojo: como el repo es público, cualquiera con el link podría verla. No pongas nada privado en las notas.

## 2. Permitir que la página guarde cambios (una vez por compu)

1. En GitHub: foto de perfil → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
2. Nombre: `casas`. Expiración: la que quieras. **Repository access → Only select repositories → casas**.
3. **Permissions → Repository permissions → Contents: Read and write**. Generar y copiar el token (empieza con `github_pat_`).
4. Abre tu página → botón **⚙️** → pega el token → **Guardar y recargar**.
5. Desde ahí, al editar una casa el botón **☁️ Guardar** sube los cambios. Los demás los ven al recargar.

Nunca pegues el token dentro de ningún archivo ni lo subas al repo.

## 3. Usar el script para leer links nuevos

Una vez, en tu compu (necesitas Python 3.9 o más nuevo):

```
git clone https://github.com/TUUSUARIO/casas.git
cd casas
pip install -r requirements.txt
```

Agregar casas (pega los links tal cual):

```
python parse.py "https://www.zillow.com/homedetails/..." "https://www.redfin.com/GA/..."
```

Completar datos vacíos de las que ya están (por ejemplo la de Realtor):

```
python parse.py --refresh
```

Después subir el resultado:

```
git add data.json
git commit -m "Actualizar casas"
git push
```

Antes de correr el script, haz `git pull` para traer lo que se editó desde la página.

### Si un portal bloquea el script

Zillow, Redfin y sobre todo Realtor.com bloquean programas. En orden de facilidad:

1. **`--browser`**: abre un Chrome real. Instala una vez con `pip install playwright` y luego `playwright install chromium`.
   ```
   python parse.py "URL" --browser
   ```
   Si sale un captcha, resuélvelo en la ventana.
2. **Guardar la página a mano**: ábrela en tu navegador, Ctrl+S (guardar como "Solo HTML"), y corre:
   ```
   python parse.py "URL" --html pagina_guardada.html
   ```
3. Llenar los datos a mano con **✏️ Editar** en la página.

### Notas

- Los campos que ya tienen valor no se sobrescriben. Para forzarlo: `--force`.
- Pisos y HOA son los datos más difíciles de leer. Si salen vacíos, el listado probablemente no los dice. Confírmalos con el agente.
