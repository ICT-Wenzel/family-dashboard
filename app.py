import streamlit as st
from datetime import datetime, timedelta
import os
from supabase import create_client, Client
import requests
import json

# Konfiguration
st.set_page_config(
    page_title="Familien-Dashboard",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Supabase Verbindung
@st.cache_resource
def init_supabase():
    try:
        # Erst Streamlit Secrets versuchen (für Cloud Deployment)
        url = st.secrets.get("SUPABASE_URL") or st.secrets.get("supabase", {}).get("url")
        key = st.secrets.get("SUPABASE_KEY") or st.secrets.get("supabase", {}).get("key")
    except (FileNotFoundError, KeyError):
        # Fallback auf Environment Variables (für lokale Entwicklung)
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
    
    if not url or not key:
        st.error("⚠️ Supabase Credentials nicht gefunden!")
        st.info("""
        **Für Streamlit Cloud:**
        Gehe zu App Settings → Secrets und füge hinzu:
        ```
        SUPABASE_URL = "https://xxxxx.supabase.co"
        SUPABASE_KEY = "dein-anon-key"
        ```
        
        **Für lokale Entwicklung:**
        Erstelle `.streamlit/secrets.toml` mit:
        ```
        SUPABASE_URL = "https://xxxxx.supabase.co"
        SUPABASE_KEY = "dein-anon-key"
        ```
        """)
        st.stop()
    
    return create_client(url, key)

supabase: Client = init_supabase()

# n8n Webhook Konfiguration (optional - nur für Kalender-Integration)
def get_n8n_config():
    """Lädt n8n Webhook URLs aus Secrets oder Environment"""
    try:
        base_url = st.secrets.get("N8N_WEBHOOK_URL") or os.environ.get("N8N_WEBHOOK_URL")
        if base_url:
            return {
                "enabled": True,
                "create_event": f"{base_url}/create-calendar-event",
                "get_events": f"{base_url}/get-calendar-events",
                "delete_event": f"{base_url}/delete-calendar-event",
                "sync_calendar": f"{base_url}/sync-google-calendar"
            }
    except:
        pass
    return {"enabled": False}

N8N_CONFIG = get_n8n_config()

# Session State initialisieren
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user' not in st.session_state:
    st.session_state.user = None
if 'family_id' not in st.session_state:
    st.session_state.family_id = None

# Farben für Kategorien
COLORS = {
    "Haushalt": "#FF6B6B",
    "Arbeit": "#4ECDC4",
    "Schule": "#45B7D1",
    "Freizeit": "#FFA07A",
    "Gesundheit": "#98D8C8"
}

# n8n Webhook Helper
def call_n8n_webhook(endpoint: str, method: str = "POST", data: dict = None, params: dict = None):
    """Hilfsfunktion für n8n Webhook-Aufrufe"""
    if not N8N_CONFIG["enabled"]:
        return None
    
    try:
        if method == "GET":
            response = requests.get(endpoint, params=params, timeout=10)
        else:
            response = requests.post(endpoint, json=data, timeout=10)
        
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.warning(f"n8n nicht erreichbar: {str(e)}")
        return None

# Authentifizierungs-Funktionen
def login_user(email, password):
    try:
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        st.session_state.user = response.user
        st.session_state.authenticated = True
        
        # Family ID laden
        family_member = supabase.table('family_members').select('*').eq('user_id', response.user.id).execute()
        if family_member.data:
            st.session_state.family_id = family_member.data[0]['family_id']
            st.session_state.user_role = family_member.data[0]['role']
            st.session_state.display_name = family_member.data[0]['display_name']
        return True
    except Exception as e:
        st.error(f"Login fehlgeschlagen: {str(e)}")
        return False

def register_user(email, password, display_name):
    # feste Familie (bestehend!)
    FIXED_FAMILY_ID = "54af62fb-2d16-4e3d-9c6d-d60cebde0151"

    try:
        # 1. User registrieren
        response = supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": { "display_name": display_name }
            }
        })

        if response.user:
            user_id = response.user.id

            # 2. User zur festen Familie hinzufügen
            supabase.table('family_members').insert({
                "family_id": FIXED_FAMILY_ID,
                "user_id": user_id,
                "role": "Member",
                "display_name": display_name
            }).execute()

            st.success("✅ Registrierung erfolgreich!")
            st.info("Sie können sich jetzt anmelden.")
            return True

        return False

    except Exception as e:
        st.error(f"Registrierung fehlgeschlagen: {str(e)}")
        return False

def logout_user():
    try:
        supabase.auth.sign_out()
        st.session_state.authenticated = False
        st.session_state.user = None
        st.session_state.family_id = None
    except Exception as e:
        st.error(f"Logout fehlgeschlagen: {str(e)}")

# Login-Seite
def login_page():
    st.title("🏠 Familien-Dashboard")
    
    tab1, tab2 = st.tabs(["Anmelden", "Registrieren"])
    
    with tab1:
        st.subheader("Anmeldung")
        col1, col2, col3 = st.columns([1, 2, 1])
        
        with col2:
            email = st.text_input("E-Mail", key="login_email")
            password = st.text_input("Passwort", type="password", key="login_password")
            
            if st.button("Anmelden", use_container_width=True):
                if login_user(email, password):
                    st.rerun()
    
    with tab2:
        st.subheader("Neues Konto erstellen")
        col1, col2, col3 = st.columns([1, 2, 1])
        
        with col2:
            reg_email = st.text_input("E-Mail", key="reg_email")
            reg_display_name = st.text_input("Dein Name", key="reg_name")
            reg_password = st.text_input("Passwort", type="password", key="reg_password")
            reg_password2 = st.text_input("Passwort wiederholen", type="password", key="reg_password2")
            
            st.caption("💡 Der erste registrierte User wird automatisch Admin der Familie")
            
            if st.button("Registrieren", use_container_width=True):
                if reg_password != reg_password2:
                    st.error("❌ Passwörter stimmen nicht überein")
                elif len(reg_password) < 6:
                    st.error("❌ Passwort muss mindestens 6 Zeichen lang sein")
                elif not reg_email or not reg_display_name:
                    st.error("❌ Bitte alle Felder ausfüllen")
                else:
                    if register_user(reg_email, reg_password, reg_display_name):
                        st.balloons()

# Kanban Board mit Supabase
def kanban_board():
    st.title("📋 Aufgabenverwaltung (Kanban)")
    
    if not st.session_state.family_id:
        st.warning("⚠️ Sie sind keiner Familie zugeordnet. Bitte kontaktieren Sie Ihren Administrator.")
        return
    
    # Neue Aufgabe hinzufügen
    with st.expander("➕ Neue Aufgabe erstellen"):
        col1, col2 = st.columns(2)
        with col1:
            title = st.text_input("Titel")
            category = st.selectbox("Kategorie", list(COLORS.keys()))
            assigned_to = st.text_input("Zugewiesen an")
        with col2:
            description = st.text_area("Beschreibung")
            priority = st.selectbox("Priorität", ["Niedrig", "Mittel", "Hoch"])
            due_date = st.date_input("Fälligkeitsdatum")
        
        if st.button("Aufgabe erstellen"):
            try:
                supabase.table('tasks').insert({
                    "family_id": st.session_state.family_id,
                    "user_id": st.session_state.user.id,
                    "title": title,
                    "description": description,
                    "category": category,
                    "priority": priority,
                    "assigned_to": assigned_to,
                    "due_date": str(due_date),
                    "status": "To-Do"
                }).execute()
                st.success("✅ Aufgabe erstellt!")
                st.rerun()
            except Exception as e:
                st.error(f"Fehler: {str(e)}")
    
    # Aufgaben laden
    try:
        response = supabase.table('tasks').select('*').eq('family_id', st.session_state.family_id).order('created_at', desc=True).execute()
        tasks = response.data
    except Exception as e:
        st.error(f"Fehler beim Laden: {str(e)}")
        return
    
    # Kanban Spalten
    col1, col2, col3 = st.columns(3)
    statuses = ["To-Do", "In Progress", "Done"]
    columns = [col1, col2, col3]
    
    for status, col in zip(statuses, columns):
        with col:
            status_tasks = [t for t in tasks if t['status'] == status]
            st.subheader(f"{status} ({len(status_tasks)})")
            
            for task in status_tasks:
                with st.container():
                    st.markdown(f"""
                    <div style="background-color: {COLORS.get(task['category'], '#CCCCCC')}20; 
                                padding: 15px; 
                                border-radius: 10px; 
                                border-left: 5px solid {COLORS.get(task['category'], "#CCCCCC")};
                                margin-bottom: 10px;">
                        <h4 style="margin: 0;">{task['title']}</h4>
                        <p style="margin: 5px 0; font-size: 0.9em;">{task.get('description', '')}</p>
                        <small>📌 {task['category']} | 👤 {task.get('assigned_to', 'Niemand')} | 📅 {task.get('due_date', 'N/A')}</small><br>
                        <small>⚡ Priorität: {task['priority']}</small>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Status ändern
                    col_a, col_b, col_c = st.columns(3)
                    with col_a:
                        if status != "To-Do" and st.button("◀", key=f"left_{task['id']}"):
                            idx = statuses.index(status)
                            supabase.table('tasks').update({"status": statuses[idx - 1]}).eq('id', task['id']).execute()
                            st.rerun()
                    with col_b:
                        if st.button("🗑️", key=f"del_{task['id']}"):
                            supabase.table('tasks').delete().eq('id', task['id']).execute()
                            st.rerun()
                    with col_c:
                        if status != "Done" and st.button("▶", key=f"right_{task['id']}"):
                            idx = statuses.index(status)
                            supabase.table('tasks').update({"status": statuses[idx + 1]}).eq('id', task['id']).execute()
                            st.rerun()

# Einkaufsliste mit Supabase
def shopping_list():
    st.title("🛒 Einkaufsliste")
    
    if not st.session_state.family_id:
        st.warning("⚠️ Sie sind keiner Familie zugeordnet.")
        return
    
    # Listen laden
    try:
        lists_response = supabase.table('shopping_lists').select('*').eq('family_id', st.session_state.family_id).execute()
        lists = lists_response.data
    except Exception as e:
        st.error(f"Fehler: {str(e)}")
        return
    
    # Neue Liste erstellen
    with st.expander("➕ Neue Liste erstellen"):
        new_list = st.text_input("Name der neuen Liste")
        if st.button("Liste erstellen") and new_list:
            try:
                supabase.table('shopping_lists').insert({
                    "family_id": st.session_state.family_id,
                    "created_by": st.session_state.user.id,
                    "name": new_list
                }).execute()
                st.success(f"✅ Liste '{new_list}' erstellt!")
                st.rerun()
            except Exception as e:
                st.error(f"Fehler: {str(e)}")
    
    if not lists:
        st.info("Noch keine Listen vorhanden. Erstellen Sie eine neue Liste!")
        return
    
    # Liste auswählen
    list_names = [l['name'] for l in lists]
    selected_list_name = st.selectbox("Liste", list_names)
    selected_list = next(l for l in lists if l['name'] == selected_list_name)
    
    # Artikel hinzufügen
    col1, col2, col3 = st.columns([3, 2, 1])
    with col1:
        item_name = st.text_input("Artikel", key="new_item")
    with col2:
        item_category = st.selectbox("Kategorie", ["Lebensmittel", "Drogerie", "Haushalt", "Sonstiges"])
    with col3:
        item_quantity = st.text_input("Menge", "1", key="quantity")
    
    if st.button("Hinzufügen", use_container_width=True) and item_name:
        try:
            supabase.table('shopping_items').insert({
                "list_id": selected_list['id'],
                "name": item_name,
                "category": item_category,
                "quantity": item_quantity,
                "is_checked": False
            }).execute()
            st.rerun()
        except Exception as e:
            st.error(f"Fehler: {str(e)}")
    
    st.divider()
    
    # Artikel laden
    try:
        items_response = supabase.table('shopping_items').select('*').eq('list_id', selected_list['id']).execute()
        items = items_response.data
    except Exception as e:
        st.error(f"Fehler: {str(e)}")
        return
    
    # Nach Kategorie gruppieren
    categories = {}
    for item in items:
        cat = item['category']
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(item)
    
    for category, cat_items in categories.items():
        st.subheader(f"📦 {category}")
        for item in cat_items:
            col1, col2 = st.columns([4, 1])
            with col1:
                checked = st.checkbox(
                    f"{item['name']} ({item['quantity']})",
                    value=item['is_checked'],
                    key=f"item_{item['id']}"
                )
                if checked != item['is_checked']:
                    supabase.table('shopping_items').update({"is_checked": checked}).eq('id', item['id']).execute()
            with col2:
                if st.button("🗑️", key=f"del_item_{item['id']}"):
                    supabase.table('shopping_items').delete().eq('id', item['id']).execute()
                    st.rerun()

 # Ferienplanung mit Premium UI
def vacation_planning():
    from datetime import datetime # Import an den Anfang verschoben
    import streamlit as st
    # Angenommen, 'supabase' ist global oder im Streamlit-Kontext verfügbar
    # Angenommen, st.session_state.family_id und st.session_state.user sind gesetzt

    st.markdown("""
    <h1 style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                font-weight: 800;
                font-size: 2.2em;
                margin-bottom: 25px;">
        🏖️ Ferien- und Urlaubsplanung
    </h1>
    """, unsafe_allow_html=True)
    
    if not st.session_state.get('family_id'):
        st.warning("⚠️ Sie sind keiner Familie zugeordnet.")
        return
    
    # Neue Ferienzeit mit Premium Card
    with st.expander("✨ Neue Ferienzeit eintragen", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            person = st.text_input("👤 Person", key="vac_person")
            vacation_type = st.selectbox("🏷️ Typ", ["Schulferien", "Urlaub", "Feiertag", "Brückentag", "Homeoffice"], key="vac_type")
            start_date = st.date_input("📅 Von", key="vac_start")
        with col2:
            title = st.text_input("✏️ Bezeichnung", key="vac_title")
            notes = st.text_area("💬 Notizen", key="vac_notes")
            end_date = st.date_input("📅 Bis", key="vac_end")
        
        if st.button("✨ Ferienzeit erstellen", use_container_width=True, type="primary") and title:
            try:
                # Annahme: 'supabase' ist definiert
                supabase.table('vacations').insert({
                    "family_id": st.session_state.family_id,
                    "user_id": st.session_state.user.id,
                    "person": person,
                    "type": vacation_type,
                    "title": title,
                    "start_date": str(start_date),
                    "end_date": str(end_date),
                    "notes": notes
                }).execute()
                st.success("✅ Ferienzeit erfolgreich eingetragen!")
                st.rerun()
            except NameError:
                st.error("❌ Fehler: Supabase-Client nicht definiert.")
            except Exception as e:
                st.error(f"❌ Fehler beim Eintragen: {str(e)}")
    
    st.divider()
    
    # Ferienzeiten laden
    try:
        # Annahme: 'supabase' ist definiert
        response = supabase.table('vacations').select('*').eq(
            'family_id', st.session_state.family_id
        ).order('start_date', desc=False).execute()
        vacations = response.data
    except NameError:
        st.error("❌ Fehler: Supabase-Client nicht definiert.")
        return
    except Exception as e:
        st.error(f"❌ Fehler beim Laden der Daten: {str(e)}")
        return
    
    # Filter und Stats
    col1, col2, col3 = st.columns([2, 2, 1])
    
    all_persons = list(set([v['person'] for v in vacations if v['person']]))
    with col1:
        filter_person = st.multiselect("👥 Nach Person filtern", all_persons, default=all_persons, key="vac_filter")
    
    with col2:
        filter_type = st.multiselect("🏷️ Nach Typ filtern", 
            ["Schulferien", "Urlaub", "Feiertag", "Brückentag", "Homeoffice"],
            default=["Schulferien", "Urlaub", "Feiertag", "Brückentag", "Homeoffice"],
            key="vac_type_filter")
    
    with col3:
        st.metric("📊 Einträge", len(vacations))
    
    st.divider()
    
    # Typ-zu-Farbe Mapping
    TYPE_COLORS = {
        "Schulferien": "#FF6B6B",
        "Urlaub": "#4ECDC4",
        "Feiertag": "#45B7D1",
        "Brückentag": "#FFA07A",
        "Homeoffice": "#98D8C8"
    }
    
    TYPE_ICONS = {
        "Schulferien": "🎒",
        "Urlaub": "✈️",
        "Feiertag": "🎉",
        "Brückentag": "🌉",
        "Homeoffice": "💻"
    }
    
    # Timeline-Ansicht
    if vacations:
        st.markdown("""
        <h2 style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                    font-weight: 800;
                    font-size: 1.6em;
                    margin-bottom: 25px;">
            📅 Timeline
        </h2>
        """, unsafe_allow_html=True)
        
        # Filtere Vacations
        filtered_vacations = [
            v for v in vacations
            if (not filter_person or v['person'] in filter_person)
            and (not filter_type or v['type'] in filter_type)
        ]
        
        if filtered_vacations:
            # Gruppiere nach Monat
            months = {}
            for vacation in filtered_vacations:
                start = datetime.strptime(vacation['start_date'], '%Y-%m-%d')
                month_key = start.strftime('%B %Y')
                if month_key not in months:
                    months[month_key] = []
                months[month_key].append(vacation)
            
            # Zeige nach Monaten gruppiert
            for month, month_vacations in months.items():
                st.markdown(f"""
                <div style="background: linear-gradient(145deg, rgba(102, 126, 234, 0.12), rgba(118, 75, 162, 0.12));
                            backdrop-filter: blur(20px);
                            padding: 16px 24px;
                            border-radius: 18px;
                            margin-bottom: 20px;
                            box-shadow: 0 8px 24px rgba(102, 126, 234, 0.15),
                                        inset 0 1px 0 rgba(255, 255, 255, 0.8);
                            border-left: 5px solid #667eea;">
                    <h3 style="margin: 0; color: #667eea; font-weight: 800; font-size: 1.3em;">
                        📆 {month}
                    </h3>
                </div>
                """, unsafe_allow_html=True)
                
                for vacation in sorted(month_vacations, key=lambda x: x['start_date']):
                    col1, col2 = st.columns([6, 1])
                    
                    with col1:
                        # Berechne Dauer
                        start = datetime.strptime(vacation['start_date'], '%Y-%m-%d')
                        end = datetime.strptime(vacation['end_date'], '%Y-%m-%d')
                        duration = (end - start).days + 1
                        
                        color = TYPE_COLORS.get(vacation['type'], '#667eea')
                        icon = TYPE_ICONS.get(vacation['type'], '📅')
                        
                        notes_html = f'''
                        <div style="background: rgba(248, 250, 252, 0.8);
                                    padding: 14px 18px;
                                    border-radius: 12px;
                                    margin-top: 16px;
                                    border-left: 3px solid {color};
                                    color: #4a5568;
                                    line-height: 1.7;
                                    font-size: 0.95em;">
                            💬 {vacation.get('notes', '')}
                        </div>
                        ''' if vacation.get('notes') else ''
                        
                        # Premium Vacation Card (HTML-Komponente)
                        st.components.v1.html(f"""
                        <!DOCTYPE html>
                        <html>
                        <head>
                            <meta charset="UTF-8">
                            <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
                            <style>
                            * {{
                                font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                                margin: 0;
                                padding: 0;
                                box-sizing: border-box;
                            }}
                            body {{
                                background: transparent;
                                padding: 10px;
                            }}
                            .vacation-card {{
                                background: linear-gradient(145deg, rgba(255, 255, 255, 0.98), rgba(248, 250, 252, 0.98));
                                backdrop-filter: blur(20px);
                                border-radius: 22px;
                                padding: 24px;
                                box-shadow: 0 12px 40px rgba(102, 126, 234, 0.12),
                                            inset 0 1px 0 rgba(255, 255, 255, 0.8);
                                border-left: 6px solid {color};
                                border: 1.5px solid rgba(102, 126, 234, 0.15);
                                transition: all 0.4s ease;
                                position: relative;
                                overflow: hidden;
                            }}
                            .vacation-card:hover {{
                                transform: translateY(-5px);
                                box-shadow: 0 20px 60px rgba(102, 126, 234, 0.2);
                            }}
                            .glossy-overlay {{
                                position: absolute;
                                top: 0;
                                left: 0;
                                right: 0;
                                height: 50%;
                                background: linear-gradient(180deg, rgba(255,255,255,0.4), transparent);
                                pointer-events: none;
                            }}
                            </style>
                        </head>
                        <body>
                            <div class="vacation-card">
                                <div class="glossy-overlay"></div>
                                
                                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px;">
                                    <div style="display: flex; align-items: center; gap: 14px;">
                                        <div style="background: linear-gradient(145deg, {color}85, {color}60);
                                                     width: 60px; height: 60px;
                                                     border-radius: 16px;
                                                     display: flex; align-items: center; justify-content: center;
                                                     font-size: 2em;
                                                     box-shadow: 0 8px 24px {color}40, inset 0 2px 4px rgba(255,255,255,0.3);">
                                            {icon}
                                        </div>
                                        <div>
                                            <div style="background: linear-gradient(145deg, {color}65, {color}40);
                                                         padding: 8px 18px;
                                                         border-radius: 12px;
                                                         display: inline-block;
                                                         color: white;
                                                         font-weight: 700;
                                                         font-size: 0.9em;
                                                         box-shadow: 0 4px 16px {color}30;
                                                         margin-bottom: 6px;">
                                                {vacation['type']}
                                            </div>
                                            <div style="color: #888; font-size: 0.85em; font-weight: 600;">
                                                ⏱️ {duration} Tag{"e" if duration != 1 else ""}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                                
                                <h3 style="margin: 16px 0 14px 0; 
                                           font-size: 1.5em; 
                                           font-weight: 800;
                                           background: linear-gradient(135deg, {color}, {color}DD);
                                           -webkit-background-clip: text;
                                           -webkit-text-fill-color: transparent;
                                           line-height: 1.3;">
                                    {vacation['title']}
                                </h3>
                                
                                <div style="background: linear-gradient(145deg, rgba(102, 126, 234, 0.12), rgba(118, 75, 162, 0.08));
                                             padding: 14px 20px;
                                             border-radius: 14px;
                                             margin: 16px 0;
                                             box-shadow: 0 4px 12px rgba(102, 126, 234, 0.08);
                                             display: flex;
                                             align-items: center;
                                             gap: 12px;
                                             flex-wrap: wrap;">
                                    <div style="font-weight: 700; color: #667eea; font-size: 1.1em;">
                                        📅 {start.strftime('%d.%m.%Y')}
                                    </div>
                                    <div style="color: #999; font-weight: 600;">→</div>
                                    <div style="font-weight: 700; color: #764ba2; font-size: 1.1em;">
                                        📅 {end.strftime('%d.%m.%Y')}
                                    </div>
                                </div>
                                
                                <div style="display: flex; gap: 10px; margin: 16px 0;">
                                    <span style="background: linear-gradient(145deg, rgba(102, 126, 234, 0.18), rgba(102, 126, 234, 0.12));
                                                 padding: 10px 18px;
                                                 border-radius: 12px;
                                                 font-size: 0.95em;
                                                 font-weight: 700;
                                                 color: #667eea;
                                                 box-shadow: 0 2px 8px rgba(102, 126, 234, 0.15);">
                                        👤 {vacation.get('person', 'N/A')}
                                    </span>
                                </div>
                                
                                {notes_html}
                            </div>
                        </body>
                        </html>
                        """, height=350)
                        # **HINWEIS:** Der ursprüngliche redundante st.markdown Block wurde hier entfernt.
                    
                    with col2:
                        # Leerraum für Ausrichtung
                        st.markdown("<br><br>", unsafe_allow_html=True) 
                        if st.button("🗑️", key=f"del_vac_{vacation['id']}", use_container_width=True, type="secondary"):
                            try:
                                # Annahme: 'supabase' ist definiert
                                supabase.table('vacations').delete().eq('id', vacation['id']).execute()
                                st.success("✅ Gelöscht!")
                                st.rerun()
                            except NameError:
                                st.error("❌ Fehler: Supabase-Client nicht definiert.")
                            except Exception as e:
                                st.error(f"❌ Fehler beim Löschen: {str(e)}")
        else:
            st.markdown("""
            <div style="text-align: center; padding: 80px 20px;
                        background: linear-gradient(145deg, rgba(102, 126, 234, 0.08), rgba(118, 75, 162, 0.08));
                        border-radius: 24px; backdrop-filter: blur(20px);
                        box-shadow: 0 8px 32px rgba(102, 126, 234, 0.12),
                                     inset 0 1px 0 rgba(255, 255, 255, 0.8);">
                <div style="font-size: 4em; margin-bottom: 20px;">🔍</div>
                <p style="color: #667eea; font-weight: 700; font-size: 1.3em;">Keine Einträge gefunden</p>
                <p style="color: #888; margin-top: 10px;">Passe deine Filter an oder erstelle neue Ferienzeiten!</p>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="text-align: center; padding: 100px 20px;
                    background: linear-gradient(145deg, rgba(102, 126, 234, 0.08), rgba(118, 75, 162, 0.08));
                    border-radius: 24px; backdrop-filter: blur(20px);
                    box-shadow: 0 8px 32px rgba(102, 126, 234, 0.12),
                                 inset 0 1px 0 rgba(255, 255, 255, 0.8);">
            <div style="font-size: 5em; margin-bottom: 20px;">🏖️</div>
            <h2 style="color: #667eea; font-weight: 800; font-size: 1.8em; margin-bottom: 10px;">
                Noch keine Ferienzeiten geplant
            </h2>
            <p style="color: #888; margin-top: 10px; font-size: 1.1em;">
                Erstelle deine erste Ferienzeit um loszulegen!
            </p>
        </div>
        """, unsafe_allow_html=True)
    
    st.divider()
    
    # Legende mit Premium Design
    with st.expander("🎨 Typ-Legende"):
        cols = st.columns(len(TYPE_COLORS))
        for i, (vac_type, color) in enumerate(TYPE_COLORS.items()):
            with cols[i]:
                icon = TYPE_ICONS.get(vac_type, "📅")
                st.markdown(f"""
                <div style="background: linear-gradient(145deg, {color}85, {color}60);
                            border-left: 5px solid {color};
                            color: white;
                            padding: 18px;
                            border-radius: 16px;
                            text-align: center;
                            font-weight: 800;
                            box-shadow: 0 8px 24px {color}40, inset 0 1px 0 rgba(255,255,255,0.3);
                            transition: all 0.3s ease;
                            cursor: pointer;
                            font-size: 1.1em;">
                    <div style="font-size: 2em; margin-bottom: 8px;">{icon}</div>
                    {vac_type}
                </div>
                """, unsafe_allow_html=True)

import streamlit as st
from datetime import datetime, timedelta

# ====================================================================
# !!! WICHTIG: DIESE PLATZHALTER MÜSSEN SIE ERSETZEN !!!
#
# Beispiel für den Supabase-Client (passen Sie dies an Ihre Initialisierung an)
# from supabase_client import supabase # ODER:
# from supabase import create_client
# SUPABASE_URL = st.secrets["SUPABASE_URL"]
# SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
# supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
#
# HIER MUSS IHR TATSÄCHLICHER SUPABASE-CLIENT EINGEFÜGT WERDEN
#
# Wenn Sie den Client NICHT importieren können, fügen Sie hier einen Platzhalter ein:
# supabase = None # Dies führt zu einem Fehler, wenn es versucht wird aufzurufen!


# Fügen Sie hier IHR COLORS-Dictionary ein.
COLORS = {
    'Arzt': '#1E90FF', 
    'Schule': '#3CB371', 
    'Sport': '#FFD700', 
    'Einkauf': '#FF4500', 
    'Privat': '#8A2BE2'
}
# ====================================================================


def weekly_schedule():
    st.title("📆 Wochenplan")
    
    # --- 1. GLOBALE CSS-KORREKTUR ---
    st.markdown("""
    <style>
        /* CSS-Stile für die optische Gestaltung (Glossy-Look, Box-Schatten, Hintergrund-Fixes) */
        .stApp {
            background-color: transparent !important;
        }

        /* HARD FIX: Verstecke alle unsichtbaren Streamlit-Blöcke (verhindert helle Boxen) */
        div[data-testid^="stHorizontalBlock"],
        div[data-testid^="stVerticalBlock"],
        div[data-testid="stBlock"] {
            background-color: transparent !important;
            box-shadow: none !important;
            border: none !important;
            padding: 0 !important;
            margin: 0 !important;
        }
        
        div[data-testid^="stVerticalBlock"] > div:empty,
        div[data-testid^="stHorizontalBlock"] > div:empty,
        div[data-testid="stBlock"] > div:empty {
            background-color: transparent !important;
            box-shadow: none !important;
            border: none !important;
        }

        /* KORREKTUR: st.divider() Linien */
        .stDivider {
            background: transparent !important;
            box-shadow: none !important;
            border: none !important;
            padding: 0 !important;
            margin: 20px 0 !important;
        }
        .stDivider > div {
            border-top: 2px solid rgba(255, 255, 255, 0.15) !important;
            height: 0 !important;
        }
        
        /* Gezielte Glossy-Anpassung der sichtbaren Streamlit-Widgets */
        .stExpander, 
        .stMultiSelect, 
        .stSelectbox, 
        .stTextInput, 
        .stTextArea, 
        .stDateInput, 
        .stTimeInput,
        div[data-testid="stForm"],
        div[data-testid="stHorizontalBlock"] > div:nth-child(2)
        {
            background: rgba(255, 255, 255, 0.08) !important;
            backdrop-filter: blur(15px) saturate(180%);
            -webkit-backdrop-filter: blur(15px) saturate(180%);
            border-radius: 18px !important;
            border: 1px solid rgba(255, 255, 255, 0.2) !important;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.3);
            padding: 15px;
            color: #f3f4f6;
        }
        
        .create-card {
            background: linear-gradient(135deg, rgba(102, 126, 234, 0.15), rgba(118, 75, 162, 0.15)) !important;
            border: 2px solid rgba(102, 126, 234, 0.4) !important;
            border-radius: 28px !important;
            box-shadow: 0 15px 45px rgba(102, 126, 234, 0.3), inset 0 2px 0 rgba(255, 255, 255, 0.4);
            padding: 0; 
        }
        .create-card .stExpander {
             box-shadow: none !important;
             border: none !important;
        }

        .delete-button-box {
            /* Nicht mehr benötigt, da die Liste weg ist, aber zur Sicherheit drin gelassen */
            background: rgba(255, 59, 48, 0.15) !important;
            backdrop-filter: blur(10px);
            border: 2px solid rgba(255, 59, 48, 0.3) !important;
            border-radius: 16px !important;
            padding: 8px !important;
            box-shadow: 0 8px 24px rgba(255, 59, 48, 0.25), inset 0 1px 0 rgba(255, 255, 255, 0.2);
            transition: all 0.3s ease;
        }
        .delete-button-box:hover {
            background: rgba(255, 59, 48, 0.25) !important;
            border-color: rgba(255, 59, 48, 0.5) !important;
            box-shadow: 0 12px 32px rgba(255, 59, 48, 0.4);
            transform: translateY(-2px);
        }
        
    </style>
    """, unsafe_allow_html=True)

    
    # Session State initialisieren
    if 'family_id' not in st.session_state:
        st.session_state.family_id = 1 
    if 'week_offset' not in st.session_state:
        st.session_state.week_offset = 0

    
    if not st.session_state.get('family_id'):
        st.warning("⚠️ Sie sind keiner Familie zugeordnet.")
        return
    
    # --- 2. NEUER TERMIN HINZUFÜGEN ---
    st.markdown('<div class="create-card">', unsafe_allow_html=True)
    with st.expander("✨ **Neuen Termin erstellen**", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            event_title = st.text_input("📝 Titel", key="event_title")
            person = st.text_input("👤 Person", key="event_person")
            # Sicherstellen, dass COLORS existiert
            category_options = list(COLORS.keys()) if 'COLORS' in globals() else ["Kategorie 1", "Kategorie 2"]
            event_category = st.selectbox("🏷️ Kategorie", category_options, key="event_cat")
        with col2:
            event_date = st.date_input("📅 Datum", key="event_date", value=datetime.now().date())
            start_time = st.time_input("🕐 Von", key="event_start", value=datetime.now().time())
            end_time = st.time_input("🕐 Bis", key="event_end", value=(datetime.now() + timedelta(hours=1)).time())
        
        description = st.text_area("💬 Beschreibung", key="event_desc")
        
        if st.button("✨ Termin erstellen", use_container_width=True, type="primary") and event_title:
            try:
                # !!! HIER IHRE SUPABASE INSERT LOGIK EINFÜGEN !!!
                # supabase.table('schedule_events').insert({...}).execute()
                st.success("✅ Termin erfolgreich erstellt! (Implementierung noch notwendig)")
                # st.rerun() 
            except Exception as e:
                st.error(f"❌ Fehler beim Erstellen: {str(e)}")
    st.markdown('</div>', unsafe_allow_html=True) 
    
    st.divider()
    
    # --- 3. DATEN LADEN & DATUMSFILTER (KORRIGIERT) ---
    today = datetime.now().date()
        
    week_offset = st.session_state.get('week_offset', 0)
    
    # Ermitteln des Start- und Enddatums der Woche (Montag bis Sonntag)
    week_start = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    week_end = week_start + timedelta(days=6)
    
    events = []
    
    try:
        # Prüfen, ob die 'supabase'-Variable überhaupt existiert
        if 'supabase' not in globals():
            st.error("❌ Kritischer Fehler: Supabase-Client ('supabase') ist nicht global verfügbar. **Bitte importieren/definieren Sie ihn korrekt am Anfang des Skripts!**")
            # Dummy-Events für UI-Test (kann später entfernt werden)
            # events = [{'title': 'Beispieltermin', 'person': 'Dummy', 'category': 'Arzt', 'event_date': str(week_start), 'start_time': '09:00:00', 'end_time': '10:00:00', 'id': 999}]
            events = [] # Leere Liste, da wir die echten Daten wollen
            
        else:
            # SUPABASE QUERY: Lädt Events NUR für die 7 Tage der aktuellen Woche.
            # Nutzung von globals()['supabase'] stellt sicher, dass auf die globale Variable zugegriffen wird
            response = globals()['supabase'].table('schedule_events')\
                .select('*')\
                .eq('family_id', st.session_state.family_id)\
                .gte('event_date', str(week_start))\
                .lte('event_date', str(week_end))\
                .order('event_date')\
                .order('start_time')\
                .execute()
            
            # Überprüfen, ob die Antwort Daten enthält
            events = response.data if hasattr(response, 'data') and response.data else [] 
            
            # Optional: Debug-Ausgabe in der Sidebar
            # st.sidebar.info(f"Loaded {len(events)} events for {week_start} to {week_end}.")
            
    except Exception as e:
        # Fängt allgemeine Verbindungs- oder Abfragefehler ab
        st.error(f"❌ Fehler beim Ausführen der Supabase-Abfrage: {str(e)}. (Überprüfen Sie Tabellennamen, Family ID und Berechtigungen)")
        events = []

    
    # --- 4. WOCHENNAVIGATION ---
    col1, col2, col3 = st.columns([1, 3, 1])
    with col1:
        if st.button("◀ Zurück", use_container_width=True, key="prev_week"):
            st.session_state.week_offset = st.session_state.get('week_offset', 0) - 1
            st.rerun()
    with col2:
        st.markdown(f"""
        <div style="text-align: center; padding: 16px; 
                      background: linear-gradient(135deg, #1f2937 0%, #0f172a 100%); 
                      border-radius: 18px; color: #9ca3af; font-weight: 700; font-size: 1.1em;
                      box-shadow: 0 10px 40px rgba(0, 0, 0, 0.5), inset 0 2px 0 rgba(255, 255, 255, 0.1);
                      border: 2px solid rgba(255, 255, 255, 0.1);">
              📅 <span style="color: white;">{week_start.strftime('%d.%m.%Y')} - {week_end.strftime('%d.%m.%Y')}</span>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        if st.button("Weiter ▶", use_container_width=True, key="next_week"):
            st.session_state.week_offset = st.session_state.get('week_offset', 0) + 1
            st.rerun()
    
    if st.session_state.get('week_offset', 0) != 0:
        if st.button("🎯 **Zurück zu heute**", use_container_width=True, key="today_btn", type="secondary"):
            st.session_state.week_offset = 0
            st.rerun()
    
    # Filter
    all_persons = list(set([e.get('person', '') for e in events if e.get('person')]))
    if all_persons:
        filter_person = st.multiselect("👥 **Nach Person filtern**", all_persons, default=all_persons, key="schedule_filter")
    else:
        filter_person = []
    
    st.divider()
    
    # --- 5. KALENDER GRID HTML ---
    time_slots = [f"{h:02d}:00" for h in range(6, 23)]
    days_of_week = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    days_short = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    
    calendar_html = '<div class="calendar-grid">'
    
    # Header
    calendar_html += '<div class="calendar-header time-header">⏰<br><span style="font-size: 0.8em;">Zeit</span></div>'
    for i, (day_name, day_short) in enumerate(zip(days_of_week, days_short)):
        day = week_start + timedelta(days=i)
        is_today_class = "today-header" if day == today else ""
        today_marker = "🔥 " if day == today else ""
        calendar_html += f'''
        <div class="calendar-header {is_today_class}">
            {today_marker}<strong>{day_short}</strong><br>
            <span style="font-size: 0.85em; opacity: 0.95;">{day.strftime("%d.%m")}</span>
        </div>
        '''
    
    # Zellen-Inhalt
    for time_slot in time_slots:
        calendar_html += f'<div class="time-label">{time_slot}</div>'
        
        for i in range(7):
            day = week_start + timedelta(days=i)
            day_str = str(day)
            is_today_class = "today" if day == today else ""
            
            # Events filtern (nach Tag, Person und Startstunde)
            day_events = [
                e for e in events 
                if e.get('event_date') == day_str
                and (not filter_person or e.get('person') in filter_person)
                and e.get('start_time', '')[:5].split(':')[0] == time_slot[:2]
            ]
            
            cell_content = ""
            for event in day_events:
                color = COLORS.get(event.get('category'), '#CCCCCC')
                event_id = event.get('id', 'temp_id')
                desc_safe = event.get('description', '').replace('"', '&quot;').replace("'", '&#39;')
                
                cell_content += f'''
                <div class="event-block" 
                      style="background: linear-gradient(145deg, {color}30, {color}15); 
                            border-left: 5px solid {color};
                            box-shadow: 0 8px 24px {color}30, inset 0 1px 0 rgba(255,255,255,0.2);" 
                      onclick="deleteEvent('{event_id}')"
                      title="🗑️ Klicken zum Löschen: {desc_safe}">
                    <div class="event-time">{event.get('start_time', '')[:5]}-{event.get('end_time', '')[:5]}</div>
                    <div class="event-title">{event.get('title', 'N/A')}</div>
                    <div class="event-person">👤 {event.get('person', 'N/A')}</div>
                    <div class="delete-hint">
                        <div style="background: rgba(255, 255, 255, 0.15); padding: 5px 10px; border-radius: 8px; margin-top: 5px; font-weight: 600;">🗑️ Löschen</div>
                    </div>
                </div>
                '''
            
            calendar_html += f'<div class="calendar-cell {is_today_class}">{cell_content}</div>'
    
    calendar_html += '</div>'
    
    # Komponenten HTML für Grid
    st.components.v1.html(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
        <style>
        .calendar-grid {{
            display: grid;
            grid-template-columns: 80px repeat(7, 1fr);
            gap: 5px;
            font-family: 'Inter', sans-serif;
            color: #f3f4f6;
            margin: 20px 0;
            padding: 10px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 18px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}
        .calendar-header {{
            padding: 10px 5px;
            text-align: center;
            font-weight: 700;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
        }}
        .today-header {{
            background: rgba(102, 126, 234, 0.3) !important;
            border: 1px solid rgba(102, 126, 234, 0.6);
        }}
        .time-header {{
            background: transparent !important;
            box-shadow: none !important;
        }}
        .time-label {{
            padding: 10px 5px;
            text-align: right;
            font-weight: 500;
            font-size: 0.9em;
            color: #9ca3af;
        }}
        .calendar-cell {{
            min-height: 80px;
            padding: 5px;
            background: rgba(255, 255, 255, 0.02);
            border-radius: 8px;
            transition: background 0.2s;
            position: relative;
            display: flex;
            flex-direction: column;
            gap: 4px;
            border: 1px dashed rgba(255, 255, 255, 0.1);
        }}
        .today {{
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.15);
        }}
        .event-block {{
            padding: 5px 8px;
            border-radius: 8px;
            font-size: 0.85em;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
            position: relative;
            overflow: hidden;
        }}
        .event-block:hover {{
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255,255,255,0.3);
        }}
        .event-title {{
            font-weight: 700;
            line-height: 1.2;
            overflow: hidden;
            white-space: nowrap;
            text-overflow: ellipsis;
        }}
        .event-time, .event-person {{
            font-size: 0.75em;
            opacity: 0.8;
            font-weight: 500;
        }}
        .delete-hint {{
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(255, 0, 0, 0.9);
            color: white;
            display: flex;
            justify-content: center;
            align-items: center;
            font-weight: bold;
            opacity: 0;
            transition: opacity 0.2s;
            z-index: 10;
        }}
        .event-block:hover .delete-hint {{
            opacity: 1;
        }}
        </style>
    </head>
    <body>
        {calendar_html}
        
        <script>
        function deleteEvent(id) {{
            // Streamlit Callback, um die ID im Session State zu speichern
            if (window.parent.document.getElementById('delete_event_id_input')) {{
                window.parent.document.getElementById('delete_event_id_input').value = id;
                window.parent.document.getElementById('delete_event_id_input').dispatchEvent(new Event('change'));
            }} else {{
                console.log('Event Löschen für ID:', id);
                alert('Termin mit ID ' + id + ' wird gelöscht. Rerun notwendig.');
            }}
        }}
        </script>
    </body>
    </html>
    """, height=2000, scrolling=True)
    
    # Event-Löschung behandeln (Logik beibehalten)
    if 'delete_event_id' in st.session_state:
        event_id = st.session_state.delete_event_id
        try:
            # !!! HIER IHRE SUPABASE DELETE LOGIK EINFÜGEN !!!
            # supabase.table('schedule_events').delete().eq('id', event_id).execute()
            st.success("✅ Termin gelöscht! (Implementierung noch notwendig)")
            del st.session_state.delete_event_id
            # st.rerun() 
        except Exception as e:
            st.error(f"❌ Fehler beim Löschen: {str(e)}")

# Hauptanwendung
def main():
    if not st.session_state.authenticated:
        login_page()
    else:
        # Sidebar
        with st.sidebar:
            st.title(f"👋 {st.session_state.get('display_name', 'Benutzer')}")
            st.caption(f"Rolle: {st.session_state.get('user_role', 'Member')}")
            
            st.divider()
            
            page = st.radio(
                "Navigation",
                ["📋 Kanban", "🛒 Einkaufsliste", "🏖️ Ferienplanung", "📆 Wochenplan"],
                label_visibility="collapsed"
            )
            
            st.divider()
            
            if st.button("🚪 Abmelden", use_container_width=True):
                logout_user()
                st.rerun()
        
        # Hauptbereich
        if "Kanban" in page:
            kanban_board()
        elif "Einkaufsliste" in page:
            shopping_list()
        elif "Ferienplanung" in page:
            vacation_planning()
        elif "Wochenplan" in page:
            weekly_schedule()

if __name__ == "__main__":
    main()