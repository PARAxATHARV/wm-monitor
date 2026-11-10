for d in www.euronics.de www.expert.de www.cyberport.de www.alternate.de www.galaxus.de ao.de www.notebooksbilliger.de www.conrad.de www.saturn.de; do
  echo "=== $d"
  curl -s -A "Mozilla/5.0" "https://$d/robots.txt" | grep -iE "^(user-agent: \*|disallow: /$|crawl-delay)" | head -5
  code=$(curl -s -o /tmp/shop.html -w "%{http_code}" -A "Mozilla/5.0" "https://$d/")
  wall=$(grep -ioE "KPSDK|cf-chl|challenge-platform|captcha|access denied|datadome|perimeterx" /tmp/shop.html | sort -u | tr '\n' ' ')
  echo "homepage: HTTP $code, size $(wc -c < /tmp/shop.html), protection: ${wall:-none}"
  sleep 2
done
