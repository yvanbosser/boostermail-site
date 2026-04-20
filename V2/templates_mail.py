"""Templates intelligents EasyMail — 45 templates fixes (tu/vous) + detection + assemblage."""
import re
import unicodedata

# === TEMPLATES FIXES ===
# type: 'incoming' (detecte sur mail recu) ou 'brief' (detecte sur brief utilisateur)

TEMPLATES = [
    # --- ACCUSES DE RECEPTION (#1-5) ---
    {'id': 1, 'type': 'incoming', 'name': 'document_recu',
     'keywords': ['ci-joint', 'piece jointe', 'document', 'transmet', 'envoie', 'joint'],
     'vous': "Bien recu, merci. Je prends connaissance du document et reviens vers vous rapidement.",
     'tu': "Bien recu, merci. Je prends connaissance du document et te reviens rapidement."},
    {'id': 2, 'type': 'incoming', 'name': 'facture_recue',
     'keywords': ['facture', 'avoir', 'note de frais'],
     'vous': "Bien recu, merci. Je prends connaissance du document et reviens vers vous rapidement.",
     'tu': "Bien recu, merci. Je prends connaissance du document et te reviens rapidement."},
    {'id': 3, 'type': 'incoming', 'name': 'planning_recu',
     'keywords': ['planning', 'calendrier', 'programme'],
     'vous': "Bien note, merci pour le planning.",
     'tu': "Bien note, merci pour le planning."},
    {'id': 4, 'type': 'incoming', 'name': 'info_simple',
     'keywords': ['note', 'entendu', 'information', 'informe', 'acte'],
     'vous': "C'est bien note, merci pour l'information.",
     'tu': "C'est bien note, merci pour l'info."},
    {'id': 5, 'type': 'incoming', 'name': 'compte_rendu',
     'keywords': ['compte rendu', 'compte-rendu', 'cr ', 'synthese', 'recap'],
     'vous': "Bien recu, merci pour ce compte-rendu.",
     'tu': "Bien recu, merci pour le CR."},

    # --- CONFIRMATIONS (#6, #8, #9) ---
    {'id': 6, 'type': 'incoming', 'name': 'rdv_confirme',
     'keywords': ['rendez-vous', 'rdv', 'confirme', 'creneau'],
     'vous': "Parfait, c'est bien note.",
     'tu': "Parfait, c'est note."},
    {'id': 8, 'type': 'incoming', 'name': 'accord_valide',
     'keywords': ['valide', 'approuve', 'accepte', 'accord', 'ok pour'],
     'vous': "Parfait, merci pour la confirmation.",
     'tu': "Parfait, merci pour la confirmation."},
    {'id': 9, 'type': 'incoming', 'name': 'bonne_execution',
     'keywords': ['effectue', 'realise', 'fait', 'termine', 'finalise', 'traite'],
     'vous': "Parfait, merci pour votre retour.",
     'tu': "Parfait, merci pour ton retour."},

    # --- REMERCIEMENTS (#10, #11) ---
    {'id': 10, 'type': 'incoming', 'name': 'merci_retour',
     'keywords': ['merci', 'remercie'],
     'vous': "Avec plaisir. N'hesitez pas si besoin.",
     'tu': "Avec plaisir, n'hesite pas."},
    {'id': 11, 'type': 'incoming', 'name': 'merci_aide',
     'keywords': ['aide', 'coup de main', 'service'],
     'vous': "Avec plaisir, c'est normal.",
     'tu': "Avec plaisir, c'est normal."},

    # --- TRANSMISSIONS (#13, #14, #15) ---
    {'id': 13, 'type': 'brief', 'name': 'envoi_document',
     'brief_keywords': ['ci-joint', 'piece jointe', 'pj'],
     'vous': "Je vous prie de bien vouloir trouver ci-joint le document demande.",
     'tu': "Tu trouveras ci-joint le document demande."},
    {'id': 14, 'type': 'brief', 'name': 'envoi_coordonnees',
     'brief_keywords': ['coordonnees', 'contact de'],
     'vous': "Vous trouverez ci-dessous les coordonnees de [A COMPLETER].",
     'tu': "Tu trouveras ci-dessous les coordonnees de [A COMPLETER]."},
    {'id': 15, 'type': 'incoming', 'name': 'reception_transfert',
     'keywords': ['transfere', 'transmis', 'fait suivre', 'forwarde'],
     'vous': "Merci pour la transmission, c'est bien note.",
     'tu': "Merci pour la transmission, c'est bien note."},

    # --- REPORTS / MISES EN ATTENTE (#16, #17, #18) ---
    {'id': 16, 'type': 'incoming', 'name': 'relance_non_traitee',
     'keywords': ['relance', 'rappel', 'en attente'],
     'vous': "Bien note, je reviens vers vous des que possible sur ce point.",
     'tu': "Bien note, je te reviens des que possible sur ce point."},
    {'id': 17, 'type': 'incoming', 'name': 'demande_maj',
     'keywords': ['avancement', 'ou en est', 'point sur', 'mise a jour', 'nouvelles'],
     'vous': "Le dossier est en cours de traitement, je vous tiens informe des sa mise a jour effectuee.",
     'tu': "Le dossier est en cours, je te tiens informe des que c'est a jour."},
    {'id': 18, 'type': 'incoming', 'name': 'question_verification',
     'keywords': ['verifier', 'verification', 'checker', 'regarder'],
     'vous': "Je verifie ce point et reviens vers vous rapidement.",
     'tu': "Je verifie ce point et te reviens rapidement."},

    # --- ACCEPTATIONS (#19, #20, #21) ---
    {'id': 19, 'type': 'incoming', 'name': 'creneau_propose',
     'keywords': ['disponible', 'dispo', 'creneau', 'convient'],
     'vous': "C'est note, [CRENEAU A CONFIRMER] me convient.",
     'tu': "C'est note, [CRENEAU A CONFIRMER] me va."},
    {'id': 20, 'type': 'incoming', 'name': 'invitation',
     'keywords': ['invitation', 'invite', 'webinar', 'evenement', 'conference'],
     'vous': "Merci pour l'invitation, je prends note.",
     'tu': "Merci pour l'invitation, je prends note."},
    {'id': 21, 'type': 'incoming', 'name': 'proposition_commerciale',
     'keywords': ['proposition', 'offre', 'decouvrir', 'solution'],
     'vous': "Merci pour votre proposition que je vais etudier. Je reviendrai vers vous si besoin.",
     'tu': "Merci pour ta proposition que je vais regarder. Je te reviens si besoin."},

    # --- FORWARDS (#25, #26, #27) ---
    {'id': 25, 'type': 'brief', 'name': 'forward_info',
     'brief_keywords': ['pour info', 'fyi', 'information'],
     'vous': "Pour information.",
     'tu': "Pour info."},
    {'id': 26, 'type': 'brief', 'name': 'forward_action',
     'brief_keywords': ['prendre en charge', 'a traiter', 'a gerer'],
     'vous': "Merci de prendre en charge ce point.",
     'tu': "Merci de prendre en charge ce point."},
    {'id': 27, 'type': 'brief', 'name': 'forward_avis',
     'brief_keywords': ['ton avis', 'votre avis', 'avis'],
     'vous': "Quel est votre avis sur ce point ?",
     'tu': "Quel est ton avis sur ce point ?"},

    # --- REFUS (#28, #29, #30) ---
    {'id': 28, 'type': 'brief', 'name': 'refus_creneau',
     'brief_keywords': ['pas dispo', 'indisponible', 'refus creneau'],
     'vous': "Je ne suis malheureusement pas disponible sur ce creneau. Auriez-vous d'autres disponibilites ?",
     'tu': "Je ne suis malheureusement pas dispo sur ce creneau. Tu aurais d'autres dispos ?"},
    {'id': 29, 'type': 'brief', 'name': 'refus_demande',
     'brief_keywords': ['refus', 'refuse', 'pas possible'],
     'vous': "Je ne suis pas en mesure de donner suite a votre demande.",
     'tu': "Je ne suis pas en mesure de donner suite a cette demande."},
    {'id': 30, 'type': 'brief', 'name': 'refus_commercial',
     'brief_keywords': ['pas interesse', 'non merci'],
     'vous': "Merci pour votre proposition, mais cela ne correspond pas a notre besoin actuel.",
     'tu': "Merci pour ta proposition, mais ca ne correspond pas a notre besoin actuel."},

    # --- RELANCES (#31, #32) ---
    {'id': 31, 'type': 'brief', 'name': 'relance_client',
     'brief_keywords': ['relance'],
     'brief_exclude': ['douce'],
     'vous': "Je me permets de revenir vers vous concernant mon precedent message. Avez-vous pu en prendre connaissance ?",
     'tu': "Je me permets de revenir vers toi concernant mon precedent message. As-tu pu en prendre connaissance ?"},
    {'id': 32, 'type': 'brief', 'name': 'relance_douce',
     'brief_keywords': ['relance douce', 'rappel doux'],
     'vous': "Sauf erreur de ma part, je n'ai pas eu de retour sur ce point.",
     'tu': "Sauf erreur de ma part, je n'ai pas eu de retour sur ce point."},

    # --- PROPOSITIONS (#33, #34) ---
    {'id': 33, 'type': 'brief', 'name': 'proposer_rdv',
     'brief_keywords': ['rdv', 'rendez-vous', 'echange'],
     'vous': "Seriez-vous disponible pour un echange a ce sujet ?",
     'tu': "Serais-tu disponible pour un echange sur ce sujet ?"},
    {'id': 34, 'type': 'brief', 'name': 'proposer_creneaux',
     'brief_keywords': ['creneaux', 'dispos', 'disponibilites'],
     'vous': "Je peux vous proposer les creneaux suivants : [A COMPLETER].",
     'tu': "Je peux te proposer les creneaux suivants : [A COMPLETER]."},

    # --- URGENCES (#35, #36) ---
    {'id': 35, 'type': 'brief', 'name': 'urgence_soft',
     'brief_keywords': ['urgent', 'rapidement'],
     'vous': "Pouvez-vous me confirmer ce point rapidement ?",
     'tu': "Peux-tu me confirmer ce point rapidement ?"},
    {'id': 36, 'type': 'brief', 'name': 'urgence_pro',
     'brief_keywords': ['prioritaire', 'urgent pro'],
     'vous': "Ce point etant prioritaire, je vous remercie de votre retour rapide.",
     'tu': "Ce point etant prioritaire, merci de ton retour rapide."},

    # --- DIVERS (#37-45) ---
    {'id': 37, 'type': 'brief', 'name': 'pj_oubliee',
     'brief_keywords': ['pj oubliee', 'piece jointe oubliee'],
     'vous': "Je vous prie de bien vouloir trouver en piece jointe le document mentionne dans mon precedent message.",
     'tu': "Tu trouveras en PJ le document mentionne dans mon precedent message."},
    {'id': 38, 'type': 'brief', 'name': 'demande_interne',
     'brief_keywords': ['regarde', 'check', 'verifie'],
     'vous': "Pourriez-vous regarder ce point et me faire un retour ?",
     'tu': "Peux-tu regarder ce point et me faire un retour ?"},
    {'id': 39, 'type': 'brief', 'name': 'assignation',
     'brief_keywords': ['assigne', 'prends en charge', 'a toi'],
     'vous': "Merci de prendre ce sujet en charge.",
     'tu': "Merci de prendre ce sujet en charge."},
    {'id': 40, 'type': 'brief', 'name': 'felicitations',
     'brief_keywords': ['felicitations', 'bravo', 'feliciter'],
     'vous': "Toutes mes felicitations, c'est une excellente nouvelle.",
     'tu': "Felicitations, c'est top !"},
    {'id': 41, 'type': 'brief', 'name': 'voeux',
     'brief_keywords': ['voeux', 'bonne annee'],
     'vous': "Je vous adresse mes meilleurs voeux pour cette nouvelle annee.",
     'tu': "Bonne annee a toi !"},
    {'id': 42, 'type': 'brief', 'name': 'excuses_delai',
     'brief_keywords': ['excuses', 'desole', 'retard', 'delai'],
     'vous': "Je vous prie de m'excuser pour ce delai de reponse.",
     'tu': "Desole pour le delai."},
    {'id': 43, 'type': 'brief', 'name': 'demande_delai',
     'brief_keywords': ['plus de temps', 'delai supplementaire'],
     'vous': "Serait-il possible d'avoir davantage de temps sur ce point ?",
     'tu': "Serait-il possible d'avoir davantage de temps sur ce point ?"},
    {'id': 44, 'type': 'brief', 'name': 'reponse_partielle',
     'brief_keywords': ['reponse partielle', 'premiers points'],
     'vous': "Je vous reponds sur les premiers points, je reviens vers vous pour le reste.",
     'tu': "Je te reponds sur les premiers points, je reviens vers toi pour le reste."},
    {'id': 45, 'type': 'brief', 'name': 'mise_en_copie',
     'brief_keywords': ['copie', 'en copie', 'cc'],
     'vous': "Je mets [NOM] en copie pour suivi.",
     'tu': "Je mets [NOM] en copie pour suivi."},
]

# Mots anglais courants pour detecter les mails en anglais
_ENGLISH_WORDS = {'thanks', 'thank', 'received', 'noted', 'regards', 'hello', 'dear', 'please',
                  'sincerely', 'best', 'kind', 'cheers', 'hi ', 'hey ', 'good morning',
                  'good afternoon', 'good evening'}


def _normalize(text):
    """Normalise un texte : minuscules + suppression accents."""
    text = text.lower()
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')


def _strip_html(text):
    """Supprime les tags HTML."""
    return re.sub(r'<[^>]+>', ' ', text).strip()


def _word_count(text):
    """Compte les mots d'un texte (apres stripping HTML)."""
    clean = _strip_html(text)
    words = [w for w in clean.split() if len(w) > 0]
    return len(words)


def _is_english(text):
    """Detecte si un texte est probablement en anglais."""
    text_lower = text.lower()
    return any(word in text_lower for word in _ENGLISH_WORDS)


def detect_template(email_body, subject, brief, is_first_mail, reply_mode,
                    importance_override=None, current_draft=None):
    """
    Detecte si un template correspond au mail/brief.
    Retourne (template_dict, template_name) ou (None, None).

    10 gardes de securite avant de proposer un template.
    """
    # Garde 7 : importance H forcee
    if importance_override == 3:
        return None, None

    # Garde 8 : brouillon existant
    if current_draft and current_draft.strip():
        return None, None

    # --- TEMPLATES BRIEF (outgoing) ---
    if brief and brief.strip():
        brief_clean = brief.strip()
        # Garde 5 : brief trop long
        if len(brief_clean) >= 20:
            return None, None
        brief_norm = _normalize(brief_clean)
        # Chercher un match dans les templates brief
        for tpl in TEMPLATES:
            if tpl['type'] != 'brief':
                continue
            # Check exclusions
            excludes = tpl.get('brief_exclude', [])
            if any(_normalize(ex) in brief_norm for ex in excludes):
                continue
            # Check keywords
            for kw in tpl.get('brief_keywords', []):
                if _normalize(kw) in brief_norm:
                    return tpl, tpl['name']
        return None, None

    # --- TEMPLATES INCOMING (mail recu simple) ---
    if reply_mode == 'forward':
        # Garde 4 : pas de templates incoming en mode forward
        return None, None

    if not email_body:
        return None, None

    body_clean = _strip_html(email_body)

    # Garde 6 : mail en anglais
    if _is_english(body_clean):
        return None, None

    # Garde 1 : mail trop long
    if _word_count(body_clean) >= 15:
        return None, None

    # Garde 2 : question
    if '?' in body_clean:
        return None, None

    # Garde 9 : normaliser pour comparaison
    body_norm = _normalize(body_clean)

    # Garde 3 : chercher un match mot-cle
    for tpl in TEMPLATES:
        if tpl['type'] != 'incoming':
            continue
        for kw in tpl.get('keywords', []):
            if _normalize(kw) in body_norm:
                return tpl, tpl['name']

    return None, None


def _score_keyword_matches(body_norm, keywords):
    """Compte combien de keywords matchent dans le body. Retourne int."""
    return sum(1 for kw in keywords if _normalize(kw) in body_norm)


def match_template_with_confidence(email_body, subject, brief, is_first_mail,
                                    reply_mode, importance_override=None,
                                    current_draft=None, learned_templates=None):
    """
    Wrapper autour de detect_template qui :
      - Calcule un score de confiance (0.0 à 1.0)
      - Consulte aussi les templates appris (`learned_templates` de la DB)
      - Retourne un dict structuré ou None

    Règle confiance (Plan 2 Phase 1.A.3 — seuil 0.75) :
      - Fixe 1 keyword match = 0.80
      - Fixe 2+ keyword matches = 0.90
      - Fixe brief match = 0.85 (brief court = signal fort)
      - Learned, tous keywords matchent = 0.85 (promoted) / 0.78 (candidate)
      - Learned demoted = ignoré
    """
    # 1. Essai sur les templates FIXES via detect_template standard
    tpl, tpl_name = detect_template(
        email_body=email_body, subject=subject, brief=brief,
        is_first_mail=is_first_mail, reply_mode=reply_mode,
        importance_override=importance_override, current_draft=current_draft,
    )
    if tpl:
        # Recalculer le score selon le nombre de keywords matchés
        if tpl.get('type') == 'brief':
            confidence = 0.85
        else:
            body_norm = _normalize(_strip_html(email_body or ''))
            n = _score_keyword_matches(body_norm, tpl.get('keywords', []))
            confidence = 0.90 if n >= 2 else 0.80
        return {
            'match': True,
            'template_id': tpl.get('id'),
            'template_name': tpl_name,
            'source': 'fixed',
            'confidence': confidence,
            'template_dict': tpl,
        }

    # 2. Essai sur les templates APPRIS (s'ils sont fournis)
    if learned_templates and email_body and reply_mode != 'forward' and not (brief and brief.strip()):
        body_clean = _strip_html(email_body or '')
        if _word_count(body_clean) < 30 and '?' not in body_clean:
            body_norm = _normalize(body_clean)
            best = None
            for lt in learned_templates:
                if lt.get('status') == 'demoted':
                    continue
                keywords = [k.strip() for k in (lt.get('pattern_keywords') or '').split(',') if k.strip()]
                if not keywords:
                    continue
                matches = _score_keyword_matches(body_norm, keywords)
                if matches == len(keywords):  # TOUS les keywords matchent
                    confidence = 0.85 if lt.get('status') == 'promoted' else 0.78
                    if not best or confidence > best['confidence']:
                        best = {
                            'match': True,
                            'template_id': lt['id'],
                            'template_name': f"learned_{lt['id']}",
                            'source': 'learned',
                            'confidence': confidence,
                            'learned': lt,
                        }
            if best:
                return best

    return None


def assemble_learned_template(learned_template, contact_profile, user_name):
    """Assemble un mail à partir d'un template appris (plus simple : texte déjà complet)."""
    register = (contact_profile or {}).get('register', 'vouvoiement')
    greeting = (contact_profile or {}).get('greeting', '') or 'Bonjour,'
    closing = (contact_profile or {}).get('closing', '') or 'Cordialement,'
    body = learned_template.get('template_text', '')
    signature = user_name or ''
    parts = [greeting, '', body, '', closing]
    if signature:
        parts.append(signature)
    return '\n'.join(parts)


def assemble_template(template_dict, contact_profile, user_name):
    """
    Assemble le mail final : greeting + corps template (tu/vous) + closing + signature.
    """
    # Determiner le registre
    register = 'vouvoiement'
    greeting = 'Bonjour,'
    closing = 'Cordialement,'

    if contact_profile and isinstance(contact_profile, dict):
        register = contact_profile.get('register', 'vouvoiement') or 'vouvoiement'
        greeting = contact_profile.get('greeting', '') or 'Bonjour,'
        closing = contact_profile.get('closing', '') or 'Cordialement,'

    # Choisir la version tu/vous
    if register == 'tutoiement':
        body = template_dict.get('tu', template_dict.get('vous', ''))
    else:
        body = template_dict.get('vous', '')

    # Signature
    signature = user_name or ''

    # Assembler
    parts = [greeting, '', body, '', closing]
    if signature:
        parts.append(signature)

    return '\n'.join(parts)
