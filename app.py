import streamlit as st
from datetime import datetime, timedelta
import os
from supabase import create_client, Client

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
                                border-left: 5px solid {COLORS.get(task['category'], '#CCCCCC')};
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
                            margin-bottom: 10px;">
                    <h4 style="margin: 0;">{vacation['title']}</h4>
                    <p style="margin: 5px 0;">📅 {vacation['start_date']} bis {vacation['end_date']}</p>
                    <small>👤 {vacation.get('person', 'N/A')} | 🏷️ {vacation['type']}</small><br>
                    <small>{vacation.get('notes', '')}</small>
                </div>
                """, unsafe_allow_html=True)
            with col2:
                if st.button("🗑️", key=f"del_vac_{vacation['id']}"):
                    supabase.table('vacations').delete().eq('id', vacation['id']).execute()
                    st.rerun()

# Wochenplan mit Supabase
def weekly_schedule():
    st.title("📆 Wochenplan")
    
    if not st.session_state.family_id:
        st.warning("⚠️ Sie sind keiner Familie zugeordnet.")
        return
    
    # Neuen Termin hinzufügen
    with st.expander("➕ Neuen Termin erstellen"):
        col1, col2 = st.columns(2)
        with col1:
            event_title = st.text_input("Titel")
            person = st.text_input("Person")
            event_category = st.selectbox("Kategorie", list(COLORS.keys()))
        with col2:
            event_date = st.date_input("Datum")
            start_time = st.time_input("Von")
            end_time = st.time_input("Bis")
        
        description = st.text_area("Beschreibung")
        
        if st.button("Termin erstellen") and event_title:
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
    try:
        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        
        response = supabase.table('schedule_events').select('*').eq('family_id', st.session_state.family_id).gte('event_date', str(week_start)).lte('event_date', str(week_end)).order('event_date', desc=False).execute()
        events = response.data
    except Exception as e:
        st.error(f"Fehler: {str(e)}")
        return
    
    # Filter
    all_persons = list(set([e['person'] for e in events if e['person']]))
    filter_person = st.multiselect("Nach Person filtern", all_persons, default=all_persons, key="schedule_filter")
    
    # Wochenansicht
    for i in range(7):
        day = week_start + timedelta(days=i)
        day_name = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"][i]
        
        st.subheader(f"{day_name}, {day.strftime('%d.%m.%Y')}")
        
        day_events = [e for e in events if e['event_date'] == str(day) and (not filter_person or e['person'] in filter_person)]
        
        if day_events:
            for event in sorted(day_events, key=lambda x: x['start_time']):
                col1, col2 = st.columns([5, 1])
                with col1:
                    st.markdown(f"""
                    <div style="background-color: {COLORS.get(event['category'], '#CCCCCC')}20; 
                                padding: 10px; 
                                border-radius: 8px; 
                                border-left: 4px solid {COLORS.get(event['category'], '#CCCCCC')};
                                margin-bottom: 8px;">
                        <strong>{event['start_time'][:5]} - {event['end_time'][:5]}</strong> | {event['title']}<br>
                        <small>👤 {event.get('person', 'N/A')} | 📌 {event['category']}</small><br>
                        <small>{event.get('description', '')}</small>
                    </div>
                    """, unsafe_allow_html=True)
                with col2:
                    if st.button("🗑️", key=f"del_event_{event['id']}"):
                        supabase.table('schedule_events').delete().eq('id', event['id']).execute()
                        st.rerun()
        else:
            st.info("Keine Termine")
        
        st.divider()

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