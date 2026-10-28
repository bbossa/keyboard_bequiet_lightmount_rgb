"""Displayed texts: English in the code, translated by a table (no gettext toolchain).

Language: LIGHTMOUNT_LANG, then the usual LANGUAGE, LC_ALL, LC_MESSAGES, LANG.
"""
import os

FR = {
    'Save': 'Enregistrer',
    'Revert': 'Annuler les modifications',
    'Live preview': 'Aperçu en direct',
    'Show the changes on the keyboard before saving':
        'Afficher les modifications sur le clavier avant de les enregistrer',
    'Zones': 'Zones',
    'New zone': 'Nouvelle zone',
    'Create a zone with the selected LEDs': 'Créer une zone avec les LED sélectionnées',
    'Add': 'Ajouter',
    'Add the selected LEDs to this zone': 'Ajouter les LED sélectionnées à cette zone',
    'Remove': 'Retirer',
    'Take the selected LEDs out of their zone': 'Retirer les LED sélectionnées de leur zone',
    'Select': 'Sélectionner',
    'Select the LEDs of this zone': 'Sélectionner les LED de cette zone',
    'Name': 'Nom',
    'Color': 'Couleur',
    'Dim': 'Atténuation',
    'Delete zone': 'Supprimer la zone',
    'Alerts': 'Alertes',
    'Zone': 'Zone',
    'Duration (s)': 'Durée (s)',
    'Notification': 'Notification',
    'Critical': 'Critique',
    'Failed command': 'Commande en échec',
    'Desktop notifications': 'Notifications du bureau',
    'Shell errors': 'Erreurs du shell',
    '{n} LEDs': '{n} LED',
    '{n} selected': '{n} sélectionnée(s)',
    'No LED selected': 'Aucune LED sélectionnée',
    'Click a key, drag to select several, Ctrl+click to add or remove, double-click to select its zone.':
        'Clic sur une touche, glisser pour en sélectionner plusieurs, Ctrl+clic pour ajouter ou retirer, '
        'double-clic pour sélectionner sa zone.',
    'Names: letters, digits, - and _ only, not already used.':
        'Noms : lettres, chiffres, - et _ uniquement, pas déjà utilisés.',
    'Saved: {path}': 'Enregistré : {path}',
    'The service rereads the config.': 'Le service relit la config.',
    'Service not running: zones applied once.': 'Service arrêté : zones appliquées une fois.',
    'Not saved: {error}': 'Non enregistré : {error}',
    'Invalid: {error}': 'Invalide : {error}',
    'Keyboard: {error}': 'Clavier : {error}',
    'Live preview stopped.': 'Aperçu en direct arrêté.',
    'Permission denied on the keyboard: is the udev rule 70-bequiet-light-mount.rules installed?':
        "Accès refusé au clavier : la règle udev 70-bequiet-light-mount.rules est-elle installée ?",
    'The config file has problems, they will be fixed on save:':
        'Le fichier de config a des problèmes, ils seront corrigés à l\'enregistrement :',
    'Unsaved changes': 'Modifications non enregistrées',
    'Save them before closing?': 'Les enregistrer avant de fermer ?',
    'Cancel': 'Annuler',
    'Discard': 'Abandonner',
    'Zone {name}': 'Zone {name}',
    'no zone': 'aucune zone',
    'Edited zone only': 'Zone éditée seule',
    'Off: every zone in its color, as on the keyboard': 'Désactivé : chaque zone dans sa couleur, comme sur le clavier',
}


def language():
    for var in ('LIGHTMOUNT_LANG', 'LANGUAGE', 'LC_ALL', 'LC_MESSAGES', 'LANG'):
        value = os.environ.get(var, '')
        if value:
            return value.split(':')[0][:2].lower()
    return 'en'


TABLE = FR if language() == 'fr' else {}


def _(text, **values):
    return TABLE.get(text, text).format(**values)
