# Routes API — Proto EasyMail

*Extrait de CLAUDE.md — section Routes principales*

## Routes Proto (app.py — port 5050)

| Route | Description |
|-------|-------------|
| `/` | Redirect vers `/inbox` |
| `/inbox` | Boite de reception (cache 60s) |
| `/email/<id>` | Detail email + lance prefetch A/B/C en background |
| `/new_mail` | Composition nouveau mail |
| `/contacts` | Page contacts (recherche, tri, edition, mot-cle) |
| `/profile` | Profil utilisateur, scoring, metriques, importance par defaut |
| `/generate_reply` POST | Generation SSE (streaming) — modes: reply, reply_all, forward, new_mail |
| `/send_reply` POST | Envoi + post-envoi (metriques, apprentissage, profils) |
| `/refine_reply` POST | Modification par instruction (non-streaming) |
| `/api/search_count` GET | Recherche mot-cle synchrone + enrichissement background |
| `/api/prefetch_status` GET | Statut du prefetch A/B/C (polling frontend) |
| `/api/style_status` GET | Statut onboarding (polling) |
| `/api/metrics` GET | Agregats metriques |
| `/api/knowledge_score` GET | Score 0-100 + milestones |
| `/api/contact_profiles` GET | Tous les profils contacts |
| `/api/contact_profile/<email>` GET | Profil d'un contact |
| `/api/analyze_contact` POST | Re-analyse forcee d'un contact |
| `/api/update_contact` POST | Edition manuelle d'un profil |
| `/api/add_contact_keyword` POST | Ajout mot-cle au profil |
| `/api/save_setting` POST | Sauvegarde reglage utilisateur |
| `/api/reanalyze_style` POST | Relance analyse de style |
| `/api/save_original_attachments/<id>` POST | Cache PJ originales en temp |
| `/api/upload_attachment` POST | Upload PJ complementaire |
| `/api/extract_file_text` POST | Extraction texte de PJ (new_mail) |
| `/api/email_html/<id>` GET | HTML body avec images base64 (pour iframe) |
| `/api/download_attachment/<id>/<index>` GET | Telechargement PJ |
| `/api/delete_email/<id>` POST | Suppression (corbeille Outlook) |
| `/echeances` | Page gestion des echeances (onglets: a venir, en retard, terminees) |
| `/api/echeances` GET | Liste echeances (filtrable par statut, correspondant) |
| `/api/echeances/<id>` PUT | Modifier statut/date/description d'une echeance |
| `/api/echeances/<id>/relance` GET | Donnees pre-remplies pour mail de relance |
| `/api/echeances/urgent` GET | Echeances <= 3j + depassees (pop-up + badge) |
| `/api/echeances/pre_scan` POST | Pre-scan echeances pendant la relecture (background, resultat en cache) |
| `/api/echeances/scan` POST | Re-scan manuel (30 derniers jours) |
| `/api/folders` GET | Arborescence dossiers Outlook (cache session COM) |
| `/api/suggest_folder/<id>` GET | Suggestion hybride de dossier : regle contact/domaine (3+) → IA fallback |
| `/api/classify_email` POST | Classement : deplace mail recu + copie envoye + marque traite + apprentissage |
| `/api/classification/post_send/<id>` GET | Polling post-envoi suggestion classement mail |
| `/api/windows_folders` GET | Arborescence dossiers Windows (cache memoire) |
| `/api/suggest_pj_folder/<id>` GET | Suggestion dossier Windows pour PJ (IA) |
| `/api/classify_pj` POST | Classement PJ : copie + renommage dans explorateur Windows |
| `/api/pj_classification/post_send/<id>` GET | Polling post-envoi suggestion classement PJ |
| `/api/smart_paperclip` GET | Trombone intelligent : suggestion dossier PJ (DB + cache, pas d'IA) |
| `/api/open_windows_folder` GET | Ouvre un dossier Windows dans l'explorateur |
| `/api/echeances/post_send/<id>` GET | Polling post-envoi echeances detectees |
| `/api/echeances/<id>/mail` GET | Lien vers le mail d'origine d'une echeance |
| `/api/echeances/search_relance_mail` GET | Recherche mail pour relance echeance |
| `/api/echeances/check_sender` GET | Verifie si un expediteur a des echeances |
| `/api/inline_images/<id>` GET | Images inline asynchrones (placeholders + chargement BG) |
| `/api/extract_attachments/<id>` POST | Extraction texte des PJ selectionnees (email_detail) |
| `/api/new_profile_toast` GET | Notification nouveau profil contact cree |
| `/api/start_onboarding` POST | Demarrage onboarding manuel |
| `/api/stop_style_analysis` POST | Arret de l'analyse de style en cours |
| `/api/settings/<key>` GET | Lecture d'un reglage utilisateur |
