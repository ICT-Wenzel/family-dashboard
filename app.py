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

# Ferienplanung mit Supabase
def vacation_planning():
    st.title("🏖️ Ferien- und Urlaubsplanung")
    
    if not st.session_state.family_id:
        st.warning("⚠️ Sie sind keiner Familie zugeordnet.")
        return
    
    # Neue Ferienzeit
    with st.expander("➕ Neue Ferienzeit eintragen"):
        col1, col2 = st.columns(2)
        with col1:
            person = st.text_input("Person")
            vacation_type = st.selectbox("Typ", ["Schulferien", "Urlaub", "Feiertag"])
            start_date = st.date_input("Von", key="vac_start")
        with col2:
            title = st.text_input("Bezeichnung")
            notes = st.text_area("Notizen")
            end_date = st.date_input("Bis", key="vac_end")
        
        if st.button("Ferienzeit erstellen") and title:
            try:
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
                st.success("✅ Ferienzeit eingetragen!")
                st.rerun()
            except Exception as e:
                st.error(f"Fehler: {str(e)}")
    
    st.divider()
    
    # Ferienzeiten laden
    try:
        response = supabase.table('vacations').select('*').eq('family_id', st.session_state.family_id).order('start_date', desc=False).execute()
        vacations = response.data
    except Exception as e:
        st.error(f"Fehler: {str(e)}")
        return
    
    # Filter
    all_persons = list(set([v['person'] for v in vacations if v['person']]))
    filter_person = st.multiselect("Nach Person filtern", all_persons, default=all_persons)
    
    # Ferienzeiten anzeigen
    for vacation in vacations:
        if not filter_person or vacation['person'] in filter_person:
            col1, col2 = st.columns([5, 1])
            with col1:
                st.markdown(f"""
                    <div style="background-color: #E3F2FD; 
                                padding: 15px; 
                                border-radius: 10px; 
                                border-left: 5px solid #2196F3;
                                margin-bottom: 10px;
                                color: black;">
                        <h4 style="margin: 0; color: black;">{vacation['title']}</h4>
                        <p style="margin: 5px 0; color: black;">📅 {vacation['start_date']} bis {vacation['end_date']}</p>
                        <small style="color: black;">👤 {vacation.get('person', 'N/A')} | 🏷️ {vacation['type']}</small><br>
                        <small style="color: black;">{vacation.get('notes', '')}</small>
                    </div>
                """, unsafe_allow_html=True)
            with col2:
                if st.button("🗑️", key=f"del_vac_{vacation['id']}"):
                    supabase.table('vacations').delete().eq('id', vacation['id']).execute()
                    st.rerun()

def weekly_schedule():
    st.title("📆 Wochenplan")
    
    if not st.session_state.family_id:
        st.warning("⚠️ Sie sind keiner Familie zugeordnet.")
        return
    
    # Neuen Termin hinzufügen - Glassmorphism Card
    with st.expander("➕ Neuen Termin erstellen", expanded=False):
        st.markdown("""
        <style>
        .stExpander {
            background: linear-gradient(135deg, rgba(255,255,255,0.1), rgba(255,255,255,0.05));
            backdrop-filter: blur(10px);
            border-radius: 20px;
            border: 1px solid rgba(255,255,255,0.18);
        }
        </style>
        """, unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            event_title = st.text_input("Titel", key="event_title")
            person = st.text_input("Person", key="event_person")
            event_category = st.selectbox("Kategorie", list(COLORS.keys()), key="event_cat")
        with col2:
            event_date = st.date_input("Datum", key="event_date")
            start_time = st.time_input("Von", key="event_start")
            end_time = st.time_input("Bis", key="event_end")
        
        description = st.text_area("Beschreibung", key="event_desc")
        
        if st.button("✨ Termin erstellen", use_container_width=True) and event_title:
            try:
                supabase.table('schedule_events').insert({
                    "family_id": st.session_state.family_id,
                    "user_id": st.session_state.user.id,
                    "title": event_title,
                    "person": person,
                    "category": event_category,
                    "event_date": str(event_date),
                    "start_time": str(start_time),
                    "end_time": str(end_time),
                    "description": description
                }).execute()
                st.success("✅ Termin erstellt!")
                st.rerun()
            except Exception as e:
                st.error(f"Fehler: {str(e)}")
    
    st.divider()
    
    # Termine laden
    today = datetime.now().date()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    
    try:
        response = supabase.table('schedule_events').select('*').eq(
            'family_id', st.session_state.family_id
        ).gte('event_date', str(week_start)).lte('event_date', str(week_end)).order('event_date', desc=False).execute()
        events = response.data
    except Exception as e:
        st.error(f"Fehler beim Laden: {str(e)}")
        return
    
    # Wochennavigation mit modernem Design
    col1, col2, col3 = st.columns([1, 3, 1])
    with col1:
        if st.button("◀ Zurück", use_container_width=True, key="prev_week"):
            st.session_state.week_offset = st.session_state.get('week_offset', 0) - 1
            st.rerun()
    with col2:
        week_offset = st.session_state.get('week_offset', 0)
        current_week_start = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
        current_week_end = current_week_start + timedelta(days=6)
        st.markdown(f"""
        <div style="text-align: center; padding: 15px; 
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    border-radius: 15px; color: white; font-weight: bold;
                    box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.37);">
            📅 {current_week_start.strftime('%d.%m.%Y')} - {current_week_end.strftime('%d.%m.%Y')}
        </div>
        """, unsafe_allow_html=True)
    with col3:
        if st.button("Weiter ▶", use_container_width=True, key="next_week"):
            st.session_state.week_offset = st.session_state.get('week_offset', 0) + 1
            st.rerun()
    
    # Heute-Button
    if st.session_state.get('week_offset', 0) != 0:
        if st.button("🔵 Zurück zu heute", use_container_width=True, key="today_btn"):
            st.session_state.week_offset = 0
            st.rerun()
    
    # Filter
    all_persons = list(set([e.get('person', '') for e in events if e.get('person')]))
    if all_persons:
        filter_person = st.multiselect("👤 Nach Person filtern", all_persons, default=all_persons, key="schedule_filter")
    else:
        filter_person = []
    
    st.divider()
    
    # Modernes Glassmorphism CSS
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    * {
        font-family: 'Inter', sans-serif;
    }
    
    .calendar-grid {
        display: grid;
        grid-template-columns: 70px repeat(7, 1fr);
        gap: 3px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 20px;
        padding: 3px;
        box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.37);
        overflow: hidden;
    }
    
    .calendar-header {
        background: linear-gradient(135deg, rgba(102, 126, 234, 0.9), rgba(118, 75, 162, 0.9));
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        color: white;
        padding: 20px 10px;
        text-align: center;
        font-weight: 700;
        font-size: 0.95em;
        border-radius: 15px;
        box-shadow: 0 4px 15px 0 rgba(31, 38, 135, 0.3);
        letter-spacing: 0.5px;
    }
    
    .calendar-header.today-header {
        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        animation: pulse 2s ease-in-out infinite;
    }
    
    @keyframes pulse {
        0%, 100% { transform: scale(1); }
        50% { transform: scale(1.05); }
    }
    
    .time-label {
        background: rgba(255, 255, 255, 0.95);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        padding: 12px 8px;
        text-align: center;
        font-size: 0.8em;
        font-weight: 600;
        color: #667eea;
        border-radius: 12px;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.05);
    }
    
    .calendar-cell {
        background: rgba(255, 255, 255, 0.9);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        min-height: 80px;
        padding: 6px;
        position: relative;
        border-radius: 12px;
        transition: all 0.3s ease;
    }
    
    .calendar-cell:hover {
        background: rgba(255, 255, 255, 1);
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(0, 0, 0, 0.1);
    }
    
    .calendar-cell.today {
        background: linear-gradient(135deg, rgba(227, 242, 253, 0.9), rgba(187, 222, 251, 0.9));
        border: 2px solid #2196F3;
        box-shadow: 0 0 20px rgba(33, 150, 243, 0.3);
    }
    
    .event-block {
        padding: 10px 12px;
        border-radius: 12px;
        margin-bottom: 6px;
        font-size: 0.85em;
        cursor: pointer;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        position: relative;
        overflow: hidden;
    }
    
    .event-block::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: linear-gradient(135deg, rgba(255,255,255,0.4), rgba(255,255,255,0.1));
        opacity: 0;
        transition: opacity 0.3s ease;
        border-radius: 12px;
    }
    
    .event-block:hover::before {
        opacity: 1;
    }
    
    .event-block:hover {
        transform: translateY(-4px) scale(1.02);
        box-shadow: 0 12px 35px rgba(0,0,0,0.25);
    }
    
    .event-time {
        font-weight: 700;
        font-size: 0.9em;
        display: flex;
        align-items: center;
        gap: 4px;
    }
    
    .event-time::before {
        content: '⏰';
        font-size: 1.1em;
    }
    
    .event-title {
        font-weight: 600;
        margin-top: 4px;
        font-size: 1em;
        line-height: 1.3;
    }
    
    .event-person {
        font-size: 0.85em;
        opacity: 0.9;
        margin-top: 4px;
        font-weight: 500;
    }
    
    .detail-card {
        background: rgba(255, 255, 255, 0.95);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border-radius: 20px;
        padding: 20px;
        margin-bottom: 12px;
        box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.15);
        border: 1px solid rgba(255, 255, 255, 0.18);
        transition: all 0.3s ease;
    }
    
    .detail-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 15px 45px 0 rgba(31, 38, 135, 0.25);
    }
    
    .category-badge {
        display: inline-block;
        padding: 8px 16px;
        border-radius: 12px;
        font-weight: 600;
        text-align: center;
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
        transition: all 0.3s ease;
    }
    
    .category-badge:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(0, 0, 0, 0.15);
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Zeitraster (6 Uhr bis 22 Uhr)
    time_slots = [f"{h:02d}:00" for h in range(6, 23)]
    
    # Header mit Wochentagen
    days_of_week = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    days_short = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    week_offset = st.session_state.get('week_offset', 0)
    week_start = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    
    # Kalender-Grid HTML generieren
    calendar_html = '<div class="calendar-grid">'
    
    # Header-Zeile
    calendar_html += '<div class="calendar-header" style="grid-column: 1;">⏰<br>Zeit</div>'
    for i, (day_name, day_short) in enumerate(zip(days_of_week, days_short)):
        day = week_start + timedelta(days=i)
        is_today_class = "today-header" if day == today else ""
        today_marker = "🔥 " if day == today else ""
        calendar_html += f'''
        <div class="calendar-header {is_today_class}">
            {today_marker}{day_short}<br>
            <span style="font-size: 0.85em; opacity: 0.9;">{day.strftime("%d.%m")}</span>
        </div>
        '''
    
    # Zeitslots und Events
    for time_slot in time_slots:
        # Zeit-Label
        calendar_html += f'<div class="time-label">{time_slot}</div>'
        
        # Für jeden Tag der Woche
        for i in range(7):
            day = week_start + timedelta(days=i)
            is_today_class = "today" if day == today else ""
            
            # Events für diesen Tag und diese Stunde finden
            day_events = [
                e for e in events 
                if e.get('event_date') == str(day) 
                and (not filter_person or e.get('person') in filter_person)
                and e.get('start_time', '')[:2] == time_slot[:2]
            ]
            
            cell_content = ""
            for event in day_events:
                color = COLORS.get(event.get('category'), '#CCCCCC')
                # Berechne hellere Variante für Glossy-Effekt
                cell_content += f'''
                <div class="event-block" 
                     style="background: linear-gradient(135deg, {color}60, {color}40);
                            border-left: 5px solid {color};
                            box-shadow: 0 6px 20px {color}30;" 
                     title="{event.get('description', '')}">
                    <div class="event-time">{event.get('start_time', '')[:5]}-{event.get('end_time', '')[:5]}</div>
                    <div class="event-title">{event.get('title', 'N/A')}</div>
                    <div class="event-person">👤 {event.get('person', 'N/A')}</div>
                </div>
                '''
            
            calendar_html += f'<div class="calendar-cell {is_today_class}">{cell_content}</div>'
    
    calendar_html += '</div>'
    
    # Kalender anzeigen
    st.markdown(calendar_html, unsafe_allow_html=True)
    
    st.divider()
    
    # Detail-Liste der Termine mit Glassmorphism
    st.markdown("""
    <h2 style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
               -webkit-background-clip: text;
               -webkit-text-fill-color: transparent;
               font-weight: 700;
               margin-bottom: 20px;">
        📋 Alle Termine dieser Woche
    </h2>
    """, unsafe_allow_html=True)
    
    week_events = [
        e for e in events
        if str(week_start) <= e.get('event_date', '') <= str(week_start + timedelta(days=6))
        and (not filter_person or e.get('person') in filter_person)
    ]
    
    if week_events:
        for event in sorted(week_events, key=lambda x: (x.get('event_date', ''), x.get('start_time', ''))):
            col1, col2 = st.columns([5, 1])
            with col1:
                event_date = datetime.strptime(event['event_date'], '%Y-%m-%d').date()
                day_name = days_of_week[event_date.weekday()]
                color = COLORS.get(event.get('category'), '#CCCCCC')
                
                st.markdown(f"""
                <div class="detail-card" style="border-left: 6px solid {color};">
                    <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 10px;">
                        <div style="background: linear-gradient(135deg, {color}60, {color}40);
                                    padding: 12px 20px; border-radius: 12px; 
                                    font-weight: 700; color: white;
                                    box-shadow: 0 4px 15px {color}30;">
                            📅 {day_name[:2]}, {event_date.strftime('%d.%m')}
                        </div>
                        <div style="background: linear-gradient(135deg, {color}50, {color}30);
                                    padding: 10px 18px; border-radius: 10px;
                                    font-weight: 600;">
                            ⏰ {event.get('start_time', '')[:5]} - {event.get('end_time', '')[:5]}
                        </div>
                    </div>
                    <h3 style="margin: 15px 0 10px 0; font-size: 1.3em; font-weight: 700; 
                               background: linear-gradient(135deg, {color}, {color}CC);
                               -webkit-background-clip: text;
                               -webkit-text-fill-color: transparent;">
                        {event.get('title', 'N/A')}
                    </h3>
                    <div style="display: flex; gap: 10px; margin: 10px 0;">
                        <span style="background: rgba(102, 126, 234, 0.15); 
                                     padding: 6px 14px; border-radius: 8px;
                                     font-size: 0.9em; font-weight: 600;">
                            👤 {event.get('person', 'N/A')}
                        </span>
                        <span style="background: linear-gradient(135deg, {color}40, {color}20); 
                                     padding: 6px 14px; border-radius: 8px;
                                     font-size: 0.9em; font-weight: 600;">
                            📌 {event.get('category', 'N/A')}
                        </span>
                    </div>
                    <p style="margin-top: 10px; color: #666; line-height: 1.6;">
                        {event.get('description', '')}
                    </p>
                </div>
                """, unsafe_allow_html=True)
            with col2:
                st.markdown("<br><br>", unsafe_allow_html=True)
                if st.button("🗑️", key=f"del_event_{event['id']}", use_container_width=True):
                    supabase.table('schedule_events').delete().eq('id', event['id']).execute()
                    st.rerun()
    else:
        st.markdown("""
        <div style="text-align: center; padding: 60px 20px;
                    background: linear-gradient(135deg, rgba(102, 126, 234, 0.1), rgba(118, 75, 162, 0.1));
                    border-radius: 20px; backdrop-filter: blur(10px);">
            <h3 style="color: #667eea; font-size: 2em;">📭</h3>
            <p style="color: #666; font-weight: 500; margin-top: 10px;">Keine Termine in dieser Woche</p>
        </div>
        """, unsafe_allow_html=True)
    
    # Legende mit modernem Design
    with st.expander("🎨 Kategorien"):
        cols = st.columns(len(COLORS))
        for i, (category, color) in enumerate(COLORS.items()):
            with cols[i]:
                st.markdown(f"""
                <div class="category-badge" 
                     style="background: linear-gradient(135deg, {color}60, {color}40);
                            border-left: 4px solid {color};
                            color: white;
                            width: 100%;">
                    <strong>{category}</strong>
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