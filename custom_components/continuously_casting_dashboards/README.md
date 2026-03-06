# Dokumentacja poprawek systemowych

## Kopia biblioteki CATT (Timeout Fix)
W tym folderze znajduje się kopia biblioteki `catt` z wprowadzonym poprawionym timeoutem (10s). 
Jeśli po aktualizacji HA lub awarii zmiany znikną, użyj poniższej komendy, aby przywrócić poprawioną wersję do systemu:

```bash
docker exec -it homeassistant cp -r /config/custom_components/continuously_casting_dashboards/catt /usr/local/lib/python3.13/site-packages/
```

## Lokalizacja w systemie:
/usr/local/lib/python3.13/site-packages/catt
