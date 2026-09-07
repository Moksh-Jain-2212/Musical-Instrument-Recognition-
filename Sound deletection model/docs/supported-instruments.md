# Supported instruments

YAMNet: **61 normalized instrument labels**. Each source label is checked against the bundled 521-label YAMNet vocabulary.

Only direct instrument predictions are included. The hosted API returns its top five labels before this filter, so supported instruments can still be omitted.

| Exact YAMNet label | Public instrument name |
| --- | --- |
| Accordion | Accordion |
| Acoustic guitar | Acoustic Guitar |
| Bagpipes | Bagpipes |
| Banjo | Banjo |
| Bass drum | Bass Drum |
| Bass guitar | Bass Guitar |
| Bowed string instrument | Bowed String Instrument |
| Brass instrument | Brass Instrument |
| Cello | Cello |
| Clarinet | Clarinet |
| Cymbal | Cymbal |
| Didgeridoo | Didgeridoo |
| Double bass | Double Bass |
| Drum | Drums |
| Drum kit | Drums |
| Drum machine | Drum Machine |
| Electric guitar | Electric Guitar |
| Electric piano | Electric Piano |
| Electronic organ | Electronic Organ |
| Flute | Flute |
| French horn | French Horn |
| Glockenspiel | Glockenspiel |
| Gong | Gong |
| Guitar | Guitar |
| Hammond organ | Hammond Organ |
| Harmonica | Harmonica |
| Harp | Harp |
| Harpsichord | Harpsichord |
| Hi-hat | Hi-Hat |
| Keyboard (musical) | Keyboard |
| Mallet percussion | Mallet Percussion |
| Mandolin | Mandolin |
| Maraca | Maraca |
| Marimba, xylophone | Marimba / Xylophone |
| Organ | Organ |
| Percussion | Percussion |
| Piano | Piano |
| Plucked string instrument | Plucked Strings |
| Rattle (instrument) | Rattle |
| Sampler | Sampler |
| Saxophone | Saxophone |
| Shofar | Shofar |
| Singing bowl | Singing Bowl |
| Sitar | Sitar |
| Snare drum | Snare Drum |
| Steel guitar, slide guitar | Steel / Slide Guitar |
| Steelpan | Steelpan |
| String section | String Section |
| Synthesizer | Synthesizer |
| Tabla | Tabla |
| Tambourine | Tambourine |
| Theremin | Theremin |
| Timpani | Timpani |
| Trombone | Trombone |
| Trumpet | Trumpet |
| Tubular bells | Tubular Bells |
| Ukulele | Ukulele |
| Vibraphone | Vibraphone |
| Violin, fiddle | Violin |
| Wind instrument, woodwind instrument | Woodwind Instrument |
| Wood block | Wood Block |
| Zither | Zither |

Gemini uses the same output vocabulary plus **Strings**, **Woodwinds**, and **Brass**. This is an application output constraint, not a fixed trained Gemini class vocabulary or an accuracy guarantee.

Excluded: Music, Speech, Singing/Vocals, Choir, Humming, Rapping, genres, environmental/human sounds, Silence, Orchestra, Musical instrument, and all other non-allowlisted labels. No generic Instrument fallback is fabricated.
