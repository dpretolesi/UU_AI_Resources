#!/bin/bash
set -e

echo "Building Pagefind index..."
npx pagefind --site site --output-path site/pagefind
echo "Pagefind index built successfully."

