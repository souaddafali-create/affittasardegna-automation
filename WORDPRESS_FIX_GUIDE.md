# Guida Fix WordPress — AffittaSardegna.it

Sito: WordPress + Elementor + JetEngine + Hello Elementor theme

---

## PROBLEMA 1 — Immagine in evidenza non visibile nel Single Blog

### Opzione A — Widget JetEngine (consigliata)

1. **WordPress → JetEngine → Listings**
2. Trova il listing template usato per il Single Post (es. "Single Post", "Blog Single")
3. Modificalo con Elementor
4. In cima, **prima del titolo**, trascina il widget **Dynamic Image** (JetEngine)
5. Impostazioni:
   - **Source:** Post Thumbnail
   - **Image Size:** Full
   - **Width:** 100%
6. Salva

### Opzione B — Snippet PHP + CSS

Se il single blog non usa un listing template JetEngine:

**CSS** — Aspetto → Personalizza → CSS aggiuntivo:

```css
/* Immagine in evidenza Single Blog */
.single-post .post-thumbnail {
  width: 100%;
  max-height: 500px;
  overflow: hidden;
  margin-bottom: 2rem;
  border-radius: 8px;
}
.single-post .post-thumbnail img {
  width: 100%;
  height: auto;
  object-fit: cover;
}
```

**PHP** — Plugin "Code Snippets" oppure functions.php del tema child:

```php
// Mostra immagine in evidenza in cima ai post del blog
add_filter( 'the_content', 'affittasardegna_prepend_featured_image' );

function affittasardegna_prepend_featured_image( $content ) {
    if ( is_singular( 'post' ) && has_post_thumbnail() && is_main_query() ) {
        $img = '<div class="post-thumbnail">' . get_the_post_thumbnail( null, 'full' ) . '</div>';
        if ( strpos( $content, 'post-thumbnail' ) === false ) {
            $content = $img . $content;
        }
    }
    return $content;
}
```

---

## PROBLEMA 2 — Pagine con template homepage sbagliato

Pagine interessate: `/cookie-policy/`, `/terms-of-service/`, `/sitemap/`, `/privacy-policy/`

### Procedura (ripetere per ognuna delle 4 pagine)

1. **Pagine → Tutte le pagine**
2. Clicca sulla pagina da correggere → **Modifica**
3. Colonna destra → **Attributi della pagina** → **Template**
4. Cambiare da qualsiasi template attuale a **"Default Template"**
5. Se la pagina e' editata con Elementor:
   - Clicca "Modifica con Elementor"
   - Ingranaggio in basso a sinistra → **Page Layout: Default** o **Elementor Full Width**
   - Rimuovere eventuali sezioni homepage e usare widget Text Editor
6. **Aggiorna/Pubblica**

| Pagina | Template corretto |
|--------|-------------------|
| Cookie Policy | Default Template |
| Terms of Service | Default Template |
| Sitemap | Default Template |
| Privacy Policy | Default Template |
