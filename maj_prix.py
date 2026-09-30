#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Menu Caillou : releve les prix les plus bas a Noumea sur l'API publique de prix.nc.

Aucune installation supplementaire : seulement Python 3 (bibliotheque standard).
Resultat : prix-nc.json (a coller dans Menu Caillou, onglet Prix), rapport.txt, et copie automatique dans le presse-papiers.
"""
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from collections import Counter
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

BASE = os.environ.get('PRIXNC_BASE', 'https://prix.nc')
PAUSE = float(os.environ.get('PRIXNC_PAUSE', '0.35'))
COMMUNE = 1  # Noumea (recherche de produits)
COMMUNE_RELEVES = '1'  # code de Noumea dans les releves de prix
AGE_MAX_MS = 120 * 24 * 3600 * 1000  # on ignore les releves de plus de 120 jours
DOSSIER = os.path.dirname(os.path.abspath(__file__))
SORTIE = os.environ.get('PRIXNC_SORTIE', 'prix-nc.json')   # nom du fichier resultat
MINIMUM = int(os.environ.get('PRIXNC_MIN', '0'))            # en dessous, on n'ecrit rien (protege les bons prix)
FUSION = os.environ.get('PRIXNC_FUSION') == '1'             # garde l'ancien prix d'un ingredient introuvable cette fois

# identifiant : (termes cherches, unite kg|L|pce, doit contenir, ne doit pas contenir, contenance d'une piece en kg ou L)
R = {
    'oignon': (['oignon'], 'kg', r'oignon', r'frit|surgel|poudre|bocal|conserve|vinaigre|aigre|chips|rondelle|echalote', None),
    'ail': (['ail'], 'kg', r'\bail\b', r'poudre|semoule|sauce|pain|beurre|fromage|granule|aioli|assaison|epice|melange|pate|creme', None),
    'carotte': (['carotte'], 'kg', r'carotte', r'rape|jus|bocal|conserve|surgel|petits? pois|boite|soupe|salade|pate', None),
    'pdt': (['pomme de terre'], 'kg', r'pommes? de terre', r'chips|puree|frite|surgel|flocon|gratin|roti|salade|boite|conserve|croquette|rosti', None),
    'tomate': (['tomate'], 'kg', r'tomate', r'concass|coulis|sauce|concentre|seche|pelee|ketchup|boite|conserve|bocal|puree|pulpe|jus|surgel|soupe|pizza|sandwich|farci|pate', None),
    'courgette': (['courgette'], 'kg', r'courgette', r'surgel|conserve|bocal|boite|gratin|poele|soupe|puree|pate', None),
    'chou': (['chou'], 'kg', r'\bchou\b', r'fleur|bruxelles|kimchi|choucroute|conserve|bocal|rave|salade', None),
    'poivron': (['poivron'], 'kg', r'poivron', r'conserve|bocal|boite|surgel|poudre|farci|pate|sauce', None),
    'concombre': (['concombre'], 'kg', r'concombre', r'cornichon|bocal|conserve|salade|sauce|creme|soin|masque', None),
    'salade': (['laitue','salade'], 'pce', r'laitue|batavia|romaine|feuille de chene|salade verte', r'sachet|sauce|assaison|vinaigrette|pate|riz|thon|poulet|composee|piemontaise|fruits|bol|boite|conserve|melange|mesclun|cesar|lardon|jambon|tomate', None),
    'avocat': (['avocat'], 'pce', r'avocat', r'huile|sauce|guacamole|creme|shampo|soin|masque|beurre|dip|puree', 0.25),
    'citron': (['citron vert','lime'], 'kg', r'citron.? vert|\blimes?\b', r'jus|sirop|the |boisson|bonbon|huile|nettoy|bouteille|soda|biere|liqueur|vinaigre|glace|sorbet', None),
    'gingembre': (['gingembre'], 'kg', r'gingembre', r'poudre|moulu|the |tisane|confit|biscuit|biere|sirop|jus|pain d|bonbon|capsule|infusion|shot|huile|pate', None),
    'champi': (['champignon'], 'kg', r'champignon', r'conserve|boite|bocal|surgel|seche|sauce|soupe|creme|pizza|poelee|lamelle|pate|farce', None),
    'igname': (['igname'], 'kg', r'igname', r'chips|farine|frite|surgel', None),
    'manioc': (['manioc'], 'kg', r'manioc', r'farine|chips|tapioca|frite|surgel|pate|gari|pain', None),
    'patate': (['patate douce'], 'kg', r'patate', r'chips|frite|surgel|puree|pate', None),
    'banane': (['banane'], 'kg', r'banane', r'chips|seche|biscuit|yaourt|jus|sirop|compote|cake|gateau|boisson|cereale|lait|glace|pate|farine|confiture', None),
    'poulet': (['poulet entier','poulet'], 'kg', r'poulet', r'nugget|cordon|pane|fume|cuisse|filet|aile|escalope|hache|saucisse|salade|sandwich|plat|boite|conserve|pilon|blanc|manchon|brochette|roti|kebab|jambon|pate|soupe|bouillon|chien|chat|croquette|sauce|tikka|curry|riz|nouille', None),
    'cuisse': (['cuisse de poulet','cuisse'], 'kg', r'cuisse', r'nugget|pane|fume|canard|dinde|lapin|grenouille|cordon|roti|sauce|jambon|pate|chien', None),
    'hache': (['hache','boeuf hache'], 'kg', r'hache', r'porc|poulet|dinde|boulette|conserve|surgel|nugget|burger|legume|soja|vegetal|tomate|sauce|lasagne|hachis|parmentier|plat|pate|oignon|herbes', None),
    'boeuf': (['boeuf'], 'kg', r'boeuf|bovin', r'hache|conserve|corned|bouillon|cube|saucisse|burger|nouille|plat|sauce|soupe|pate|fume|tacos|ravioli|chili|bourguignon|surgel|chien|chat|croquette|kebab|carpaccio|seche|grison|pizza|riz|sandwich|arome|epice|assaison|marinade', None),
    'saucisse': (['saucisse'], 'kg', r'saucisse', r'seche|cocktail|aperitif|strasbourg|lentille|conserve|boite|bocal|chien|chat|surgel|choucroute|hot ?dog|knacki|chorizo|pate|pizza|sandwich', None),
    'cerf': (['cerf'], 'kg', r'cerf', r'pate|saucisson|conserve|terrine|rillette|fume|seche|chien|nourriture|croquette|biscuit|bonbon', None),
    'poisson': (['thon','mahi','wahoo','marlin','poisson frais'], 'kg', r'thon|mahi|wahoo|marlin|poisson', r'boite|conserve|surgel|pane|baton|fume|huile|sauce|sardine|maquereau|chat|chien|litiere|salade|rillette|pate|croquette|nugget|plat|riz|pizza|sandwich|tartinable|bouillon|soupe', None),
    'crevette': (['crevette'], 'kg', r'crevette', r'chips|cracker|nem|beignet|sauce|soupe|salade|plat|riz|nouille|bouillon|cocktail|conserve|boite|bocal|pate|sushi|rouleau|arome|pizza|croquette|chien|chat|epice|assaison', None),
    'moule': (['moules'], 'kg', r'\bmoules?\b', r'a gateau|a muffin|a tarte|a cake|a glacon|silicone|patisserie|four|cuisson|bougie|savon|moulinex|moulin(?!s)|congelation|bac|conserve|boite|bocal|surgele|plat|sauce toute|bisque|soupe|pate|rillette|mariniere', None),
    'pain': (['pain de mie', 'baguette'], 'pce', r'pain|baguette', r'perdu|epice|surgele|viennois(?!erie)|chien|chat|savon|niche|escalope|chapelure|farine|bebe|infantile|tambour|magique|electrique|sauce|epaule', 1),
    'beurre': (['beurre'], 'pce', r'beurre', r'cacahuete|karite|corps|cacao|visage|solaire|epice|sauce|biscuit|cookie|gateau|patisserie|chien|chat|massage', 0.25),
    'confiture': (['confiture'], 'pce', r'confiture', r'lait concentre|de canard|oignon(?!s? confit)', 1),
    'cafe': (['cafe moulu', 'cafe soluble'], 'pce', r'\bcafe\b', r'creme|glace|liqueur|biere|bonbon|chocolat|the |infusion|gateau|creme dessert|yaourt|capsule compatible', 1),
    'lait': (['lait demi ecreme', 'lait entier'], 'L', r'\blait\b', r'coco|amande|soja|avoine|riz|concentre|chocolat|fraise|\bcreme\b|beurre|poudre|bebe|infantile|corps|visage|demaquillant|solaire|savon|cheveux', None),
    'cereales': (['cereales petit dejeuner'], 'pce', r'cereale', r'barre|biscuit|bebe|infantile|chien|chat|liqueur|whisky', 1),
    'thonconserve': (['thon boite'], 'pce', r'thon', r'frais|surgele|steak|pave|tartare|sushi|chat|croquette|filet.*frais', 1),
    'mayonnaise': (['mayonnaise'], 'pce', r'mayonnaise', r'light.*sauce.*salade|allegee.*sauce', 1),
    'yaourt': (['yaourt nature'], 'pce', r'yaourt', r'glace|boisson lactee(?!.*yaourt)|creme dessert|masque|soin|cheveux', None),
    'bananefruit': (['banane'], 'kg', r'\bbanane', r'cuire|poingo|plantain|chips|seche|confiture|glace|yaourt|smoothie|jus|gateau|bebe|infantile|liqueur', None),
    'mangue': (['mangue'], 'kg', r'\bmangue', r'confiture|jus d|seche|chutney|glace|sirop|the |the$|infusion|smoothie|yaourt', None),
    'ananas': (['ananas'], 'kg', r'\bananas', r'confiture|jus d|conserve|boite|glace|sirop|chips|the |smoothie|yaourt', None),
    'pasteque': (['pasteque'], 'kg', r'\bpasteque', r'jus|glace|sirop|bonbon|chewing', None),
    'orange': (['orange'], 'kg', r'\borange', r'jus d|confiture|soda|fleur|the |sirop|bonbon|glace|chocolat|liqueur|boisson', None),
    'pamplemousse': (['pamplemousse'], 'kg', r'\bpamplemousse', r'jus d|confiture|soda|sirop|glace', None),
    'papaye': (['papaye'], 'kg', r'\bpapaye', r'confiture|jus d|seche|glace|sirop|smoothie|savon|creme|soin', None),
    'jambon': (['jambon'], 'kg', r'jambon', r'cru|sec|pizza|sandwich|quiche|croque|salade|chien|puree|pate|mousse|beurre|fromage|feuillet|nouille|tartinable|plat|omelette|gratin|lardon', None),
    'oeuf': (['oeuf','oeufs frais'], 'pce', r'\boeufs?\b', r'chocolat|paques|kinder|plat|mayonn|nouille|pate|poudre|lait|cocotte|dur|coque|colorant|gaufre|crepe|biscuit|tapioca|jaune|blanc|liquide|surprise|cadeau|jouet|decor|teinture|ballon|gel|shampo|creme|omelette|salade|sandwich|pain', None),
    'creme': (['creme fraiche','creme'], 'pce', r'creme.*fraiche|fraiche.*creme', r'soin|jour|nuit|main|visage|corps|solaire|glace|dessert|chocolat|vanille|patissiere|vegetal|soja|anti|depil|rasage|bebe|hydra|pommade|douche|chantilly', 0.2),
    'fromage': (['fromage rape','rape'], 'kg', r'(fromage|emmental|gruyere|mozzarella|cheddar).*rape|rape.*(fromage|emmental|gruyere|mozzarella|cheddar)', r'pizza|plat|carotte|coco|legume|sauce|chips|snack|sandwich|burger|salade|tartinable|cracker|epice|assaison', None),
    'riz': (['riz'], 'kg', r'\briz\b', r'cuisine|saute|cantonais|pudding|lait|souffle|galette|gateau|vinaigre|farine|cracker|nouille|sauce|plat|salade|micro|express|the |boisson|dessert|huile|papier|cereale|barre|vermicelle|sushi|bouillie|creme|boite|conserve|chien|chat|croquette|pate|cake|snack|chips|semoule|bebe|infantile|onigiri|maki|tofu', None),
    'pates': (['spaghetti','pates'], 'kg', r'spaghetti|pates|coquillette|penne|tagliatelle|fusilli|macaroni', r'fraiche|brisee|feuilletee|sablee|levee|pizza|tartiner|amande|dentifrice|fruit|boite|conserve|chien|chat|sauce|plat|salade|cuisine|carbonara|bolognaise|lasagne|ravioli|tortellini|instantane|nouille|riz|cheveux|bebe|pate a|pate de', None),
    'lentille': (['lentille'], 'kg', r'lentille', r'boite|conserve|cuisine|saucisse|salade|soupe|plat|chips|pate|bocal|prepar|cuit|micro|sachet', None),
    'pois': (['pois chiche'], 'pce', r'pois chiche', r'houmous|hummus|salade|plat|falafel|farine|chips|creme|tartinable|snack|cuisine|puree', None),
    'haricot': (['haricot rouge'], 'pce', r'haricot.*rouge|rouge.*haricot|kidney', r'salade|plat|chili|cuisine|sec|graine|prepar|boeuf|viande|sauce', None),
    'tomconc': (['tomate concassee','tomate pelee'], 'pce', r'concass|pelee', r'plat|sauce|pizza|coulis|pate|chips|tapenade|soupe', None),
    'coco': (['lait de coco'], 'pce', r'lait de coco|lait coco', r'eau|huile|rape|shampo|biscuit|glace|boisson|sirop|sucre|farine|chips|dessert|yaourt|savon|soin|poudre|curry|riz|soupe|cheveux', 0.4),
    'mais': (['mais'], 'pce', r'mais doux', r'pop|chips|huile|farine|cereale|semoule|gateau|chien|tortilla|surgel|epi|frais|creme|salade|plat|soupe|riz', None),
    'ptpois': (['petits pois'], 'pce', r'petits? pois', r'chiche|surgel|plat|soupe|puree|cuisine|salade|carotte|chips|snack|cassoulet|creme', None),
    'concentre': (['concentre de tomate','concentre'], 'pce', r'concentre.*tomate|tomate.*concentre', r'jus|sirop|fruit|cafe|lessive|bouillon|soupe|volaille|legume|boeuf|poisson|fond|fumet|arome', None),
    'farine': (['farine'], 'kg', r'farine', r'coco|riz|manioc|sarrasin|mais|avoine|chataigne|lait|bebe|infantile|poisson|complete|chien|chat|croquette|pois|soja|epeautre|pate|gateau|preparation|cake|biscuit|pain|gaufre|crepe|pizza|melange|levure|gluten|amande|noisette|banane|patate|igname|taro|lupin|lin|seigle|orge|millet|quinoa|tapioca', None),
    'huile': (['huile'], 'L', r'huile.*(tournesol|colza|vegetale|arachide|friture)|(tournesol|colza|vegetale|arachide).*huile', r'olive|massage|moteur|bain|corps|visage|essentielle|sesame|coco|argan|noix|thon|sardine|vidange|lubrifi|cheveux|amande|ricin|bebe|solaire|soin|lotion|tondeuse|chaine|outil|bois|teck|barbecue|beurre|savon|cire|shampo|graisse|spray|aerosol|degrippant|nettoy', None),
    'soja': (['sauce soja'], 'L', r'sauce.*soja|soja.*sauce', r'lait|boisson|yaourt|dessert|graine|pousse|steak|proteine|nouille|tofu|germe|creme|sucree|barbecue|nem|riz|plat', None),
    'curry': (['curry'], 'pce', r'curry', r'poulet|plat|riz|nouille|sauce|boite|soupe|pate|coco|lait|chips|cuisine|instantane|legume|pomme|creme|vindaloo|tikka|masala', None),
}


def norm(s):
    s = str(s or '').lower().replace('\u0153', 'oe')
    s = unicodedata.normalize('NFD', s)
    return ''.join(c for c in s if not unicodedata.combining(c))


def nom_enseigne(s):
    s = re.sub(r'\s+', ' ', str(s or '')).strip()
    return re.sub(r'[^\W\d_]+', lambda m: m.group(0).capitalize(), s)


# Enseignes qui ne sont pas des magasins d'alimentation : leurs relevés sont ignorés.
# Pour en ajouter une, ajoute son nom (majuscules ou minuscules, peu importe) dans cette liste.
# Motifs (mot entier, insensible aux accents/majuscules) des enseignes à ignorer
# car elles ne vendent pas au grand public. Pour en ajouter une, ajoute son motif ici.
MAGASINS_EXCLUS = [
    r'\bcheval\b',  # Cheval Distribution : grossiste, pas de vente au public
]


def magasin_exclu(nom):
    n = norm(nom)
    return any(re.search(m, n) for m in MAGASINS_EXCLUS)


class Refus(Exception):
    pass


def appel(url):
    derniere = None
    for essai in range(3):
        req = urllib.request.Request(url, headers={'Accept': 'application/json', 'User-Agent': 'MenuCaillou/1.0'})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code in (403, 429) or e.code >= 500:
                raise Refus('le service prix.nc a répondu avec l\'erreur %d' % e.code)
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            derniere = e
            time.sleep(1.5)
    raise ConnectionError('impossible de joindre prix.nc (%s)' % derniere)


def recherche(terme, page):
    url = '%s/api/v1/produitsprix/search?nom=%s&communeIds=%d&page=%d&size=50' % (
        BASE, urllib.parse.quote(terme), COMMUNE, page)
    j = appel(url)
    return (j.get('_embedded') or {}).get('produitsprix') or []


def enseigne_moins_chere(id_produit, vus):
    """Premier releve recent a Noumea, du moins cher au plus cher (les prix en promotion passent apres)."""
    maintenant = time.time() * 1000
    promo = None
    total = 1
    page = 0
    while page < min(total, 5):
        url = '%s/api/v1/relevesprix/search/findByIdProduitInOrderByPrixParUniteAscPrixAscMagasinAsc?idProduit=%s' % (
            BASE, urllib.parse.quote(str(id_produit)))
        if page:
            url += '&page=%d' % page
        j = appel(url)
        time.sleep(PAUSE)
        total = (j.get('page') or {}).get('totalPages') or 1
        for r in (j.get('_embedded') or {}).get('relevesprix') or []:
            vus[str(r.get('idCommune'))] += 1
            if str(r.get('idCommune')) != COMMUNE_RELEVES:
                continue
            if magasin_exclu(r.get('magasin')):
                continue
            d = r.get('dateReleve')
            if isinstance(d, (int, float)) and maintenant - d > AGE_MAX_MS:
                continue
            try:
                if not float(r.get('prixParUnite')) > 0:
                    continue
            except (TypeError, ValueError):
                continue
            if r.get('promotion'):
                promo = promo or r
                continue
            return r
        page += 1
    return promo


def coords_magasin(id_magasin, cache):
    """Latitude/longitude d'un magasin (mises en cache : un magasin peut revenir pour plusieurs ingrédients)."""
    if not id_magasin:
        return None
    if id_magasin in cache:
        return cache[id_magasin]
    coords = None
    try:
        j = appel('%s/api/v1/magasins/%s' % (BASE, urllib.parse.quote(str(id_magasin))))
        time.sleep(PAUSE)
        for cle_lat, cle_lon in (('latitude', 'longitude'), ('lat', 'lon'), ('lat', 'lng')):
            try:
                lat, lon = float(j.get(cle_lat)), float(j.get(cle_lon))
                if lat and lon:
                    coords = {'lat': round(lat, 5), 'lon': round(lon, 5)}
                    break
            except (TypeError, ValueError):
                continue
    except Refus:
        raise
    except Exception:
        coords = None
    cache[id_magasin] = coords
    return coords


def genre_unite(p):
    u = norm(p.get('uniteLabelCourt') or p.get('uniteLabel') or '')
    if u == 'kg':
        return 'kg'
    if u == 'l':
        return 'L'
    if u in ('g', 'ml', 'cl', '100g', '100ml', 'm', 'cm'):
        return '?'
    return 'u'


def mediane(v):
    n = len(v)
    return v[(n - 1) // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def copier(texte):
    commandes = []
    if sys.platform.startswith('win'):
        commandes = [['clip']]
    elif sys.platform == 'darwin':
        commandes = [['pbcopy']]
    else:
        commandes = [['wl-copy'], ['xclip', '-selection', 'clipboard'], ['xsel', '-b', '-i']]
    for c in commandes:
        try:
            subprocess.run(c, input=texte.encode('utf-8'), check=True, timeout=10)
            return True
        except Exception:
            continue
    return False


def main():
    print('Menu Caillou : relevé des prix sur prix.nc (Nouméa)')
    print('Compte 2 à 3 minutes. Ne ferme pas cette fenêtre.\n')
    prix, rapport, enseignes, communes_vues, magasins, cache_coords = {}, [], {}, Counter(), {}, {}
    ids = list(R)
    try:
        for i, ident in enumerate(ids, 1):
            termes, unite, doit, ne_doit_pas, contenance = R[ident]
            print('[%2d/%d] %s' % (i, len(ids), ident))
            vus = {}
            for terme in termes:
                for page in range(3):
                    items = recherche(terme, page)
                    for p in items:
                        vus[p.get('idProduit') or p.get('id')] = p
                    time.sleep(PAUSE)
                    if len(items) < 50:
                        break
            candidats = []
            for p in vus.values():
                n = norm('%s %s' % (p.get('nom', ''), p.get('variete', '')))
                if not re.search(doit, n) or re.search(ne_doit_pas, n):
                    continue
                try:
                    valeur = float(p.get('meilleurPrixParUnite'))
                except (TypeError, ValueError):
                    continue
                if not valeur > 0:
                    continue
                genre = genre_unite(p)
                v = None
                facteur = 1
                if unite == 'kg' and genre == 'kg':
                    v = valeur
                elif unite == 'L' and genre == 'L':
                    v = valeur
                elif unite == 'pce':
                    if genre == 'u':
                        v = valeur
                    elif contenance and genre != '?':
                        v = valeur * contenance
                        facteur = contenance
                if v and v > 0:
                    candidats.append((v, p.get('nom', ''), p.get('idProduit') or p.get('id'), facteur))
            candidats.sort(key=lambda c: c[0])
            bas = candidats[:3]
            if not bas:
                rapport.append('%s : aucun produit trouvé (le prix de départ reste utilisé)' % ident)
                continue
            ref = bas[(len(bas) - 1) // 2]  # produit du milieu parmi les moins chers
            val = ref[0]
            enseigne = ''
            try:
                r = enseigne_moins_chere(ref[2], communes_vues) if ref[2] else None
            except Refus:
                raise
            except Exception:
                r = None
            if r:
                val = float(r['prixParUnite']) * ref[3]
                enseigne = nom_enseigne(r.get('magasin'))
                if enseigne and enseigne not in magasins:
                    c = coords_magasin(r.get('idMagasin'), cache_coords)
                    if c:
                        magasins[enseigne] = c
            prix[ident] = int(round(val))
            if enseigne:
                enseignes[ident] = enseigne
            rapport.append('%s : %d F chez %s  (produit : %s ; les 3 moins chers : %s)' % (
                ident, prix[ident], enseigne or 'enseigne inconnue', ref[1],
                ' | '.join('%s %d' % (c[1], round(c[0])) for c in bas)))
    except Refus as e:
        print('\nArrêt : %s.' % e)
        print('Réessaie plus tard. Aucun prix n\'a été modifié.')
        return 1
    except ConnectionError as e:
        print('\nArrêt : %s.' % e)
        print('Vérifie ta connexion internet puis relance.')
        return 1

    if len(prix) < MINIMUM:
        print('\nSeulement %d prix trouvés (minimum attendu : %d). Rien n\'est modifié.' % (len(prix), MINIMUM))
        return 1
    chemin = os.path.join(DOSSIER, SORTIE)
    if FUSION:
        try:
            with open(chemin, encoding='utf-8') as f:
                ancien = json.load(f)
        except Exception:
            ancien = {}
        nouveaux = set(prix)
        gardes = {k: v for k, v in (ancien.get('stores') or {}).items() if k not in nouveaux}
        gardes.update(enseignes)
        enseignes = gardes
        fusion = dict(ancien.get('prices') or {})
        fusion.update(prix)
        prix = fusion
        magasins_fusion = dict(ancien.get('magasins') or {})
        magasins_fusion.update(magasins)
        magasins = magasins_fusion
    resultat = {'source': 'prix.nc', 'commune': 'Noumea', 'date': date.today().isoformat(), 'prices': prix, 'stores': enseignes, 'magasins': magasins}
    texte = json.dumps(resultat, separators=(',', ':'))
    with open(chemin, 'w', encoding='utf-8') as f:
        f.write(texte)
    with open(os.path.join(DOSSIER, 'rapport.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(rapport) + '\n')
        f.write('\nCodes de commune vus dans les relevés : %s\n' % dict(communes_vues.most_common(8)))

    print('\n%d prix trouvés sur %d ingrédients, dont %d avec leur enseigne et %d avec ses coordonnées.' % (len(prix), len(ids), len(enseignes), len(magasins)))
    if not enseignes:
        print('ATTENTION : aucune enseigne de Nouméa identifiée (voir la fin de rapport.txt).')
    print('Détail des produits retenus : rapport.txt (dans le même dossier).\n')
    if os.environ.get('CI'):
        print('Fichier écrit : %s' % SORTIE)
    elif copier(texte):
        print('Le résultat est COPIÉ. Ouvre Menu Caillou > Prix > « Coller et appliquer ».')
    else:
        print('Copie automatique impossible. Ouvre %s, copie tout son contenu,' % SORTIE)
        print('puis colle-le dans Menu Caillou > Prix.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
