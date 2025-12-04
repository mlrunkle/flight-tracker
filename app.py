import streamlit as st
import pandas as pd
from google_calendar import get_travel_events
from serpapi_handler import search_flights
from gcp_storage import upload_results
import config


def main():
    # Page config
    st.set_page_config(page_title="Flight Tracker", layout="wide")
    st.title("✈️ Multi-City Flight Tracker")

    # Sidebar – Configuration
    st.sidebar.header("⚙️ Search Configuration")
    
    # Departure city input
    departure_city = st.sidebar.text_input(
        "Departure City (3-letter code)", 
        value=config.DEFAULT_DEPARTURE,
        max_chars=3,
        help="Enter the 3-letter airport code for your departure city"
    ).upper()
    
    # Destination cities input
    st.sidebar.subheader("Destination Cities")
    destinations_text = st.sidebar.text_area(
        "Enter up to 10 destination cities (one per line)",
        value='\n'.join(config.DEFAULT_DESTINATIONS),
        height=200,
        help="Enter 3-letter airport codes, one per line"
    )
    
    # Airline filter
    st.sidebar.subheader("Airline Filter")
    airline_filter = st.sidebar.selectbox(
        "Filter by Airline (optional)",
        options=["All Airlines", "American Airlines", "Delta", "United", "Southwest", "JetBlue", "Spirit", "Frontier"],
        index=0,
        help="Filter results to show only flights from selected airline"
    )
    
    # Parse destinations
    destinations = [d.strip().upper() for d in destinations_text.split('\n') if d.strip()]
    destinations = destinations[:10]  # Limit to 10
    
    # Validate airport codes
    valid_departure = len(departure_city) == 3 and departure_city.isalpha()
    valid_destinations = all(len(d) == 3 and d.isalpha() for d in destinations)
    
    if not valid_departure:
        st.sidebar.error("⚠️ Departure city must be a 3-letter code")
    if not valid_destinations:
        st.sidebar.error("⚠️ All destination cities must be 3-letter codes")
    
    st.sidebar.info(f"📍 Monitoring {len(destinations)} destination(s)")
    
    # Sidebar – Trip selection
    st.sidebar.header("📅 Your Vacation Periods")
    try:
        events_df = get_travel_events()
    except Exception as e:
        st.sidebar.error(f"Error fetching calendar events: {e}")
        st.stop()

    if events_df.empty:
        st.sidebar.info("No upcoming vacation periods found.")
        st.stop()

    trip_name = st.sidebar.selectbox("Select a Vacation Period", events_df['Event'])
    trip = events_df[events_df['Event'] == trip_name].iloc[0]
    outbound_date = trip['Start'].split('T')[0]
    return_date = trip['End'].split('T')[0]

    # Main section – Flight search
    st.subheader(f"Flight Search: {departure_city} → Multiple Destinations")
    st.markdown(f"**Vacation Dates:** {outbound_date} to {return_date}")
    st.markdown(f"**Destinations:** {', '.join(destinations)}")

    if st.sidebar.button("🔍 Search All Flights", disabled=not (valid_departure and valid_destinations)):
        with st.spinner(f"Fetching flights for {len(destinations)} destinations..."):
            all_flights = []
            progress_bar = st.progress(0)
            
            for idx, dest in enumerate(destinations):
                try:
                    st.caption(f"Searching {departure_city} → {dest}...")
                    flights_json = search_flights(departure_city, dest, trip['Start'], trip['End'])
                    
                    # Parse flights for this destination
                    for f in flights_json.get('best_flights', []):
                        for flight in f.get('flights', []):
                            all_flights.append({
                                'Destination': dest,
                                'Airline': flight.get('airline'),
                                'Flight Number': flight.get('flight_number', 'N/A'),
                                'Price (USD)': f.get('price'),
                                'Duration': f.get('total_duration'),
                                'Departure': flight.get('departure_airport', {}).get('time'),
                                'Arrival': flight.get('arrival_airport', {}).get('time'),
                                'Layovers': f.get('layovers', [])
                            })
                    
                    # Also check other_flights if best_flights is empty
                    if not flights_json.get('best_flights'):
                        for f in flights_json.get('other_flights', [])[:5]:  # Limit to 5 from other flights
                            for flight in f.get('flights', []):
                                all_flights.append({
                                    'Destination': dest,
                                    'Airline': flight.get('airline'),
                                    'Flight Number': flight.get('flight_number', 'N/A'),
                                    'Price (USD)': f.get('price'),
                                    'Duration': f.get('total_duration'),
                                    'Departure': flight.get('departure_airport', {}).get('time'),
                                    'Arrival': flight.get('arrival_airport', {}).get('time'),
                                    'Layovers': f.get('layovers', [])
                                })
                    
                except Exception as e:
                    st.warning(f"⚠️ Error searching {dest}: {e}")
                
                # Update progress
                progress_bar.progress((idx + 1) / len(destinations))
            
            progress_bar.empty()

        # Display results
        if not all_flights:
            st.warning("❌ No flights found for any destination.")
        else:
            flights_df = pd.DataFrame(all_flights)
            
            # Show unique airlines found in results (for debugging)
            unique_airlines = flights_df['Airline'].dropna().unique()
            with st.expander("📋 Airlines found in results"):
                st.write(sorted(unique_airlines))
            
            # Apply airline filter if selected
            if airline_filter != "All Airlines":
                original_count = len(flights_df)
                # Make filter more flexible - match partial names
                filter_word = airline_filter.split()[0]  # Get first word (e.g., "American" from "American Airlines")
                flights_df = flights_df[flights_df['Airline'].str.contains(filter_word, case=False, na=False)]
                
                if len(flights_df) == 0 and original_count > 0:
                    st.warning(f"⚠️ No flights found matching '{airline_filter}'. Check the airlines list above to see available options.")
                elif len(flights_df) < original_count:
                    st.info(f"🔍 Filtered to {airline_filter}: showing {len(flights_df)} of {original_count} flights")
            
            # Sort by price
            flights_df = flights_df.sort_values('Price (USD)', ascending=True)
            
            st.success(f"✅ Found {len(flights_df)} total flight options across {len(destinations)} destinations!")
            
            # Display summary metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Cheapest Flight", f"${flights_df['Price (USD)'].min()}")
            with col2:
                best_dest = flights_df.loc[flights_df['Price (USD)'].idxmin(), 'Destination']
                st.metric("Best Deal", best_dest)
            with col3:
                st.metric("Total Options", len(flights_df))
            
            # Display full table
            st.dataframe(
                flights_df,
                use_container_width=True,
                hide_index=True
            )

            # Option to save (save all results combined)
            if st.button("💾 Save All Results to Cloud"):
                try:
                    combined_results = {
                        'departure': departure_city,
                        'destinations': destinations,
                        'dates': {'outbound': outbound_date, 'return': return_date},
                        'flights': all_flights
                    }
                    path = upload_results(combined_results, prefix='multi_city_search')
                    st.success(f"✅ Saved to GCP at: {path}")
                except Exception as e:
                    st.error(f"❌ Error uploading to cloud: {e}")

if __name__ == '__main__':
    main()