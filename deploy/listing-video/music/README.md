# Listing Video music beds

Drop **commercially-licensed, royalty-free** audio files (`.mp3` / `.m4a` /
`.wav`) into this directory; it is baked into the pitch-video-worker image at
the path configured by `LISTING_VIDEO_MUSIC_DIR`, and the filenames you list
in `LISTING_VIDEO_MUSIC_TRACKS` (comma-separated) appear in the studio's
music dropdown.

## Licensing rules (read before adding a track)

1. **You must hold a commercial license** covering SaaS redistribution /
   sync into customer videos that will be posted to TikTok and Instagram.
   Keep the license receipt/PDF next to the track in this repo.
2. **Do NOT use Meta AudioCraft / MusicGen output.** The released MusicGen
   weights are licensed **CC-BY-NC (non-commercial)** — output generated with
   them cannot be sold in RevOS. Generating our own beds requires a model
   whose weights AND training-data terms allow commercial use (e.g. Stable
   Audio Open under its community license terms — verify the current terms
   and our revenue against its threshold before adopting).
3. **Do not use TikTok's / Instagram's in-app music libraries** — those
   licenses cover in-app creation only, not videos uploaded via API.
4. Good sources of properly licensed beds: one-time buyout packs
   (AudioJungle/Envato with the correct broadcast license tier), Artlist /
   Epidemic Sound business plans (check their API/SaaS redistribution
   terms), or commissioning a composer for a flat-fee full-buyout pack —
   at RevOS's scale a one-time ~$1–2k buyout of 10 tracks is the cleanest
   option (no per-video royalties, no takedown risk for agents).

Naming: keep filenames short and human-readable — they're shown (without
extension) in the dropdown, e.g. `warm-piano.mp3`, `upbeat-pop.mp3`,
`cinematic-strings.mp3`.
