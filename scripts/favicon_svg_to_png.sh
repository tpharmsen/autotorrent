#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status
set -e

INPUT_SVG="logo.svg"
# Set your desired background color (Hex format: #RRGGBB)
BG_COLOR="#000000"

echo "Generating non-transparent icons from $INPUT_SVG..."

# 1. Standard Favicon (32x32)
inkscape "$INPUT_SVG" \
  --export-filename="favicon-32x32.png" \
  --export-width=32 \
  --export-height=32 \
  --export-background="$BG_COLOR" \
  --export-background-opacity=0.0

# 2. Apple Touch Icon (180x180 - Required for iOS)
inkscape "$INPUT_SVG" \
  --export-filename=tmp.png \
  --export-width=140 \
  --export-height=140 \
  --export-background="$BG_COLOR" \
  --export-background-opacity=0.0

magick tmp.png \
  -alpha on \
  -gravity center \
  -background none \
  -extent 180x180 \
  apple-touch-icon.png

# 3. Large Favicon/PWA Icon (192x192)
inkscape "$INPUT_SVG" \
  --export-filename="icon-192x192.png" \
  --export-width=192 \
  --export-height=192 \
  --export-background="$BG_COLOR" \
  --export-background-opacity=0.0

# 4. Splash Screen/Large PWA Icon (512x512)
inkscape "$INPUT_SVG" \
  --export-filename="icon-512x512.png" \
  --export-width=512 \
  --export-height=512 \
  --export-background="$BG_COLOR" \
  --export-background-opacity=0.0

echo "🎉 Success! All icons generated with a solid $BG_COLOR background."
