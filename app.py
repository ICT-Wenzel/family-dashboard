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

# Um die Funktion auszuführen, müssten Sie sie in Ihrer Streamlit-Anwendung aufrufen
# vacation_planning()

import streamlit as st
from datetime import datetime, timedelta

# Importe wie in Ihrer Umgebung erwartet (angenommen)
# from supabase_client import supabase
# from your_config import COLORS 

# ANNAHME: COLORS ist ein Dictionary mit {Kategorie: Farbcode}
COLORS = {
    "Freizeit": "#ff8c00", # Dunkleres Orange
    "Schule": "#2196F3",   # Blau
    "Arbeit": "#4CAF50",   # Grün
    "Sonstiges": "#9C27B0" # Lila
}

def weekly_schedule():
    st.title("📆 Wochenplan")
    
    # --- 1. Allgemeine CSS-Anpassung für Streamlit-Hintergründe (Kontrast/Transparenz) ---
    st.markdown("""
    <style>
        /* Allgemeiner Hintergrund transparent oder leicht dunkel */
        .stApp {
            background-color: transparent !important;
        }

        /* Container, die standardmäßig weiß sind, transparent/glasig machen */
        .stBlock, .stExpander, .stMarkdown, .stSelectbox, .stTextInput, .stTextArea, .stTimeInput, .stDateInput, .stMultiSelect {
            /* Hintergrund: Sehr helle, transparente Farbe mit Glossy/Acryl-Effekt */
            background: rgba(255, 255, 255, 0.08) !important; /* Etwas weniger transparent für besseren Kontrast */
            backdrop-filter: blur(15px) saturate(180%);
            -webkit-backdrop-filter: blur(15px) saturate(180%);
            border-radius: 18px !important;
            border: 1px solid rgba(255, 255, 255, 0.2) !important; /* Dickere/sichtbarere Grenze */
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.3); /* Stärkere Schatten */
            padding: 15px;
            color: #f3f4f6; /* Textfarbe heller für besseren Kontrast */
        }
        
        /* Spezielle Anpassung für den "Neuen Termin hinzufügen" Expander */
        .stExpander .stBlock {
            padding: 0;
            border: none !important;
            box-shadow: none !important;
            background: transparent !important;
        }

        /* Eingabefelder selbst im inneren Expander */
        .stTextInput > div > div > input,
        .stSelectbox > div > div,
        .stTextArea > div > textarea,
        .stDateInput > div > div > input,
        .stTimeInput > div > div > input {
            background: rgba(255, 255, 255, 0.15) !important;
            border: 1px solid rgba(255, 255, 255, 0.4) !important;
            color: white !important;
            border-radius: 12px !important;
            transition: all 0.3s ease;
        }

        /* Labels heller machen */
        .stForm label {
            color: #e5e7eb !important; /* Sehr hell für maximalen Kontrast */
            font-weight: 600;
        }
        
        /* Spezielles Design für die Create-Card */
        .create-card {
            background: linear-gradient(135deg, rgba(102, 126, 234, 0.15), rgba(118, 75, 162, 0.15)) !important;
            backdrop-filter: blur(25px) saturate(180%);
            -webkit-backdrop-filter: blur(25px) saturate(180%);
            border-radius: 28px !important;
            border: 2px solid rgba(102, 126, 234, 0.4) !important;
            padding: 20px !important;
            margin-bottom: 25px !important;
            box-shadow: 0 15px 45px rgba(102, 126, 234, 0.3), inset 0 2px 0 rgba(255, 255, 255, 0.4);
        }
        
        /* CORRECTION: Streamlit Haupttitel Farbe korrigiert (falls Streamlit default zu dunkel ist) */
        h1 {
            color: #e5e7eb !important; 
        }
        
        /* CORRECTION: Container-Titel H2 (für die Detail-Liste) */
        .stMarkdown h2 {
            font-size: 1.8em;
            font-weight: 800;
            color: #e5e7eb; /* Standard-Textfarbe des Containers */
        }
        
    </style>
    """, unsafe_allow_html=True)

    
    if not st.session_state.get('family_id'):
        st.warning("⚠️ Sie sind keiner Familie zugeordnet.")
        return
    
    # Neuer Termin hinzufügen
    st.markdown('<div class="create-card">', unsafe_allow_html=True)
    with st.expander("✨ **Neuen Termin erstellen**", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            event_title = st.text_input("📝 Titel", key="event_title")
            person = st.text_input("👤 Person", key="event_person")
            event_category = st.selectbox("🏷️ Kategorie", list(COLORS.keys()), key="event_cat")
        with col2:
            event_date = st.date_input("📅 Datum", key="event_date", value=datetime.now().date())
            start_time = st.time_input("🕐 Von", key="event_start", value=datetime.now().time())
            end_time = st.time_input("🕐 Bis", key="event_end", value=(datetime.now() + timedelta(hours=1)).time())
        
        description = st.text_area("💬 Beschreibung", key="event_desc")
        
        if st.button("✨ Termin erstellen", use_container_width=True, type="primary") and event_title:
            try:
                # SUPABASE-FUNKTION BEIBEHALTEN
                supabase.table('schedule_events').insert({
                    "family_id": st.session_state.family_id,
                    "user_id": st.session_state.user.id, # Angenommen st.session_state.user existiert
                    "title": event_title,
                    "person": person,
                    "category": event_category,
                    "event_date": str(event_date),
                    "start_time": str(start_time),
                    "end_time": str(end_time),
                    "description": description
                }).execute()
                st.success("✅ Termin erfolgreich erstellt!")
                st.rerun() 
            except Exception as e:
                st.error(f"❌ Fehler: {str(e)}")
    st.markdown('</div>', unsafe_allow_html=True)
    
    st.divider()
    
    # Termine laden
    today = datetime.now().date()
    week_offset_raw = st.session_state.get('week_offset', 0)
    week_start = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset_raw)
    week_end = week_start + timedelta(days=6)
    
    try:
        # SUPABASE-FUNKTION BEIBEHALTEN
        response = supabase.table('schedule_events').select('*').eq(
            'family_id', st.session_state.family_id
        ).gte('event_date', str(week_start)).lte('event_date', str(week_end)).order('event_date', desc=False).execute()
        events = response.data
    except Exception as e:
        st.error(f"❌ Fehler beim Laden: {str(e)}")
        events = [] # Sicherstellen, dass events immer eine Liste ist
    
    # Wochennavigation
    col1, col2, col3 = st.columns([1, 3, 1])
    with col1:
        if st.button("◀ Zurück", use_container_width=True, key="prev_week"):
            st.session_state.week_offset = st.session_state.get('week_offset', 0) - 1
            st.rerun()
    with col2:
        current_week_start = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset_raw)
        current_week_end = current_week_start + timedelta(days=6)
        st.markdown(f"""
        <div style="text-align: center; padding: 16px; 
                      background: linear-gradient(135deg, #1f2937 0%, #0f172a 100%); 
                      border-radius: 18px; color: #9ca3af; font-weight: 700; font-size: 1.1em;
                      box-shadow: 0 10px 40px rgba(0, 0, 0, 0.5), inset 0 2px 0 rgba(255, 255, 255, 0.1);
                      border: 2px solid rgba(255, 255, 255, 0.1);">
              📅 <span style="color: white;">{current_week_start.strftime('%d.%m.%Y')} - {current_week_end.strftime('%d.%m.%Y')}</span>
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
    
    # Kalender-Logik (unverändert)
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
    
    # Zeitslots und Events
    for time_slot in time_slots:
        calendar_html += f'<div class="time-label">{time_slot}</div>'
        
        for i in range(7):
            day = week_start + timedelta(days=i)
            is_today_class = "today" if day == today else ""
            
            day_events = [
                e for e in events 
                if e.get('event_date') == str(day) 
                and (not filter_person or e.get('person') in filter_person)
                and e.get('start_time', '')[:2] == time_slot[:2]
            ]
            
            cell_content = ""
            for event in day_events:
                color = COLORS.get(event.get('category'), '#CCCCCC')
                event_id = event['id']
                cell_content += f'''
                <div class="event-block" 
                      style="background: linear-gradient(145deg, {color}20, {color}10);
                            border-left: 5px solid {color};
                            box-shadow: 0 8px 24px {color}30, inset 0 1px 0 rgba(255,255,255,0.2);" 
                      onclick="deleteEvent('{event_id}')"
                      title="🗑️ Klicken zum Löschen: {event.get('description', '')}">
                    <div class="event-time">{event.get('start_time', '')[:5]}-{event.get('end_time', '')[:5]}</div>
                    <div class="event-title">{event.get('title', 'N/A')}</div>
                    <div class="event-person">👤 {event.get('person', 'N/A')}</div>
                    <div class="delete-hint">🗑️ Löschen</div>
                </div>
                '''
            
            calendar_html += f'<div class="calendar-cell {is_today_class}">{cell_content}</div>'
    
    calendar_html += '</div>'
    
    # --- 2. CSS im iframe anpassen (für Kalenderraster: Transparenz, Glossy, Professionalität) ---
    st.components.v1.html(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
        <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }}
        
        body {{
            background: transparent; 
            padding: 0; 
            min-height: 100vh;
            color: #d1d5db; 
        }}
        
        .calendar-grid {{
            display: grid;
            grid-template-columns: 75px repeat(7, 1fr);
            gap: 6px; 
            background: rgba(255, 255, 255, 0.08); /* Etwas dunklerer Glas-Hintergrund */
            backdrop-filter: blur(20px) saturate(180%);
            -webkit-backdrop-filter: blur(20px) saturate(180%);
            border-radius: 28px;
            padding: 6px;
            box-shadow: 
                0 25px 70px rgba(0, 0, 0, 0.5), 
                0 0 0 1px rgba(255, 255, 255, 0.1) inset; 
        }}
        
        .calendar-header {{
            background: linear-gradient(145deg, rgba(102, 126, 234, 0.9), rgba(118, 75, 162, 0.9));
            backdrop-filter: blur(25px) saturate(180%);
            -webkit-backdrop-filter: blur(25px) saturate(180%);
            color: white;
            padding: 22px 12px;
            text-align: center;
            font-weight: 800;
            border-radius: 20px;
            box-shadow: 
                0 8px 30px rgba(102, 126, 234, 0.4),
                inset 0 2px 0 rgba(255, 255, 255, 0.3); 
            border: 1px solid rgba(255, 255, 255, 0.2);
            position: relative;
            overflow: hidden;
        }}
        
        .calendar-header.today-header {{
            background: linear-gradient(145deg, #f093fb 0%, #f5576c 100%);
            animation: todayPulse 4s ease-in-out infinite;
            box-shadow: 
                0 0 40px rgba(245, 87, 108, 0.7),
                0 10px 30px rgba(240, 147, 251, 0.5),
                inset 0 2px 0 rgba(255, 255, 255, 0.5);
            border: 2px solid rgba(255, 255, 255, 0.4);
        }}
        
        .time-label {{
            background: rgba(255, 255, 255, 0.15); /* Kontrastreicher */
            backdrop-filter: blur(15px);
            -webkit-backdrop-filter: blur(15px);
            padding: 14px 10px;
            text-align: center;
            font-weight: 700;
            color: #b1b3fb; /* Helleres lila */
            border-radius: 16px;
            box-shadow: 
                0 4px 16px rgba(0, 0, 0, 0.2),
                inset 0 1px 0 rgba(255, 255, 255, 0.2); /* Stärkerer Glossy */
            border: 1px solid rgba(255, 255, 255, 0.2);
        }}
        
        .calendar-cell {{
            background: rgba(255, 255, 255, 0.05); 
            backdrop-filter: blur(15px) saturate(180%);
            -webkit-backdrop-filter: blur(15px) saturate(180%);
            min-height: 90px;
            padding: 8px;
            position: relative;
            border-radius: 16px;
            transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 
                0 2px 10px rgba(0, 0, 0, 0.15),
                inset 0 1px 0 rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.08);
        }}
        
        .calendar-cell.today {{
            background: rgba(33, 150, 243, 0.1); 
            border: 3px solid #2196F399; /* Dickerer Rand */
        }}
        
        .event-block {{
            padding: 12px 14px;
            border-radius: 16px;
            margin-bottom: 8px;
            font-size: 0.85em;
            cursor: pointer;
            transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
            backdrop-filter: blur(25px);
            -webkit-backdrop-filter: blur(25px);
            position: relative;
            overflow: hidden;
            border: 1px solid rgba(255, 255, 255, 0.3);
            color: white; 
        }}
        
        .event-time, .event-title, .event-person {{
            color: white !important; 
            text-shadow: 0 1px 3px rgba(0, 0, 0, 0.8); /* Stärkerer Schatten für Text */
        }}
        
        .event-title {{
            font-weight: 700;
            margin-top: 4px;
        }}
        
        .delete-hint {{
            /* Unverändert, da es bei Hover funktioniert */
        }}
        </style>
    </head>
    <body>
        {calendar_html}
        
        <script>
        function deleteEvent(eventId) {{
            if (confirm('Möchten Sie diesen Termin wirklich löschen?')) {{
                // Sende Nachricht an Streamlit
                window.parent.postMessage({{
                    type: 'streamlit:setComponentValue',
                    value: {{ delete_event_id: eventId }}
                }}, '*');
            }}
        }}
        </script>
    </body>
    </html>
    """, height=2000, scrolling=True)
    
    # Event-Löschung behandeln
    if 'delete_event_id' in st.session_state:
        event_id = st.session_state.delete_event_id
        try:
            # SUPABASE-FUNKTION BEIBEHALTEN
            supabase.table('schedule_events').delete().eq('id', event_id).execute()
            st.success("✅ Termin gelöscht!")
            del st.session_state.delete_event_id
            st.rerun() 
        except Exception as e:
            st.error(f"❌ Fehler beim Löschen: {str(e)}")
    
    st.divider()
    
    # --- 3. KORREKTUR: Detail-Liste Titel und HTML-Behandlung ---
    # Korrekter, kontrastreicher Titel für die Detail-Liste
    st.markdown("""
    <h2 style="font-size: 1.8em; font-weight: 800; margin-bottom: 25px; color: #e5e7eb; /* Heller Titel */
              text-shadow: 0 2px 4px rgba(0, 0, 0, 0.5);">
        📋 **Alle Termine dieser Woche**
    </h2>
    """, unsafe_allow_html=True)
    
    week_events = [
        e for e in events
        if str(week_start) <= e.get('event_date', '') <= str(week_start + timedelta(days=6))
        and (not filter_person or e.get('person') in filter_person)
    ]
    
    if week_events:
        for event in sorted(week_events, key=lambda x: (x.get('event_date', ''), x.get('start_time', ''))):
            col1, col2 = st.columns([6, 1])
            with col1:
                event_date = datetime.strptime(event['event_date'], '%Y-%m-%d').date()
                day_name = days_of_week[event_date.weekday()]
                color = COLORS.get(event.get('category'), '#CCCCCC')
                
                # --- WICHTIG: KORREKTUR DER HTML-FEHLERBEHEBUNG ---
                # Unerwünschtes HTML in der Beschreibung maskieren, um Anzeigefehler zu vermeiden.
                # Wichtig: Wir müssen sicherstellen, dass die Beschreibung komplett als Text interpretiert wird.
                description_safe = event.get('description', '').replace('<', '&lt;').replace('>', '&gt;')
                
                st.markdown(f"""
                <div style="background: linear-gradient(145deg, rgba(255, 255, 255, 0.1), rgba(248, 250, 252, 0.05));
                            backdrop-filter: blur(20px);
                            border-radius: 24px;
                            padding: 24px;
                            margin-bottom: 20px;
                            box-shadow: 0 15px 50px rgba(0, 0, 0, 0.3), 
                                        inset 0 1px 0 rgba(255, 255, 255, 0.2);
                            border-left: 6px solid {color};
                            border: 1.5px solid rgba(255, 255, 255, 0.2); /* Bessere Sichtbarkeit des Rahmens */
                            transition: all 0.4s ease;">
                    
                    <div style="display: flex; align-items: center; gap: 16px; margin-bottom: 14px; flex-wrap: wrap;">
                        <div style="background: linear-gradient(145deg, {color}CC, {color}A0); /* Kontrastreicherer Header-Chip */
                                    padding: 12px 20px; border-radius: 16px; 
                                    font-weight: 800; color: white;
                                    box-shadow: 0 6px 20px {color}40, inset 0 1px 0 rgba(255,255,255,0.4);
                                    font-size: 0.95em;">
                            📅 {day_name[:2]}, {event_date.strftime('%d.%m')}
                        </div>
                        <div style="background: linear-gradient(145deg, {color}A0, {color}80);
                                    padding: 10px 18px; border-radius: 14px;
                                    font-weight: 700; color: white;
                                    box-shadow: 0 4px 16px {color}30;">
                            ⏰ {event.get('start_time', '')[:5]} - {event.get('end_time', '')[:5]}
                        </div>
                    </div>
                    
                    <h3 style="margin: 16px 0 12px 0; font-size: 1.6em; font-weight: 900; 
                                 color: #e5e7eb; /* Titel auf helles Weiß geändert */
                                text-shadow: 0 3px 6px rgba(0, 0, 0, 0.6);">
                        {event.get('title', 'N/A')}
                    </h3>
                    
                    <div style="display: flex; gap: 12px; margin: 16px 0; flex-wrap: wrap;">
                        <span style="background: rgba(255, 255, 255, 0.2); /* Kontrastreicherer Chip */
                                    padding: 8px 16px; border-radius: 12px;
                                    font-size: 0.95em; font-weight: 700; color: #f3f4f6; /* Heller Text */
                                    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);">
                            👤 {event.get('person', 'N/A')}
                        </span>
                        <span style="background: linear-gradient(145deg, {color}40, {color}20); 
                                    padding: 8px 16px; border-radius: 12px;
                                    font-size: 0.95em; font-weight: 700; color: white;
                                    box-shadow: 0 2px 8px {color}25;">
                            📌 {event.get('category', 'N/A')}
                        </span>
                    </div>
                    
                    <p style="margin-top: 14px; color: #a1a1aa; line-height: 1.7; font-size: 1em;">
                        {description_safe}
                    </p>
                </div>
                """, unsafe_allow_html=True)
            with col2:
                # Füge einen kleinen Abstand hinzu, damit der Button besser ausgerichtet ist
                st.markdown("<br><br>", unsafe_allow_html=True) 
                if st.button("🗑️", key=f"del_event_list_{event['id']}", use_container_width=True, type="secondary"):
                    # SUPABASE-FUNKTION BEIBEHALTEN
                    supabase.table('schedule_events').delete().eq('id', event['id']).execute()
                    st.success("✅ Gelöscht!")
                    st.rerun() 
    else:
        # Kein Termine-Container
        st.markdown("""
        <div style="text-align: center; padding: 80px 20px;
                    background: linear-gradient(145deg, rgba(102, 126, 234, 0.1), rgba(118, 75, 162, 0.1)); /* etwas kontrastreicher */
                    border-radius: 28px; backdrop-filter: blur(20px);
                    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2),
                                 inset 0 1px 0 rgba(255, 255, 255, 0.15);
                    border: 1px solid rgba(255, 255, 255, 0.15);">
            <div style="font-size: 4em; margin-bottom: 20px;">📭</div>
            <p style="color: #9ca3af; font-weight: 700; font-size: 1.3em;">Keine Termine in dieser Woche</p>
            <p style="color: #a1a1aa; margin-top: 10px;">Erstelle einen neuen Termin um loszulegen!</p>
        </div>
        """, unsafe_allow_html=True)
    
    # Legende (unverändert)
    with st.expander("🎨 **Kategorien & Legende**"):
        cols = st.columns(len(COLORS))
        for i, (category, color) in enumerate(COLORS.items()):
            with cols[i]:
                st.markdown(f"""
                <div style="background: linear-gradient(145deg, {color}85, {color}60);
                            border-left: 5px solid {color};
                            color: white;
                            padding: 16px;
                            border-radius: 16px;
                            text-align: center;
                            font-weight: 700;
                            box-shadow: 0 8px 24px {color}40, inset 0 1px 0 rgba(255,255,255,0.4);
                            transition: all 0.3s ease;
                            cursor: pointer;
                            border: 1px solid rgba(255, 255, 255, 0.2);">
                    {category}
                </div>
                """, unsafe_allow_html=True)

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