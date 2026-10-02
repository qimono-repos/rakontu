# RAKONTU

RAKONTU is a small command-line tool that turns a video into a storyboard. Point it at a URL, and it downloads the video, samples a frame every few seconds, and asks a vision model to describe each moment: what is happening and which software is on screen. The result is a frame-by-frame narration you can skim in seconds instead of watching the whole thing.

## CLI shape

`ash
rakontu -u "https://youtube.com/watch?v=abc"
rakontu -u "https://youtube.com/watch?v=abc" -i 5 -o rakonto.md
`

For the flags, my suggestion is to keep them conventional (-u/--url, -i/--interval, -o/--output) rather than using Esperanto flags like --el. The command name already carries the identity. Esperanto flags would make the tool harder to use without adding much meaning, which runs against Rule 6 (pronounceability, or here, typeability, wins). If you want an Easter egg, --rakonto could be an alias for --output.
