import streamlit as st
import pandas as pd

def run():
    st.title("🏗️ BidLite Estimator - Prototype")
    st.markdown("This is a rapid prototype of the 'Lite' estimating software workflow. It acts as a smart calculator using a pre-built Master Price Book.")

    # Master Catalog (The Database)
    CATALOG = {
        "8\" SDR 35 PVC Mainline": {"Category": "Sewer", "UOM": "LF", "Labor": 18.0, "Equip": 15.0, "Material": 12.0},
        "48\" Precast Manhole": {"Category": "Sewer", "UOM": "EA", "Labor": 400.0, "Equip": 350.0, "Material": 1200.0},
        "4\" Sewer Lateral": {"Category": "Sewer", "UOM": "LF", "Labor": 12.0, "Equip": 10.0, "Material": 8.0}
    }

    if 'bid_items' not in st.session_state:
        st.session_state.bid_items = []

    # Sidebar
    with st.sidebar:
        st.header("Project Details")
        project_name = st.text_input("Project Name", "New Sewer Subdivision")
        markup_pct = st.slider("Overhead & Profit Markup (%)", 0, 50, 15)

    # Add Item Section
    st.subheader("1. Add Bid Items")
    # Pure vertical layout for maximum mobile compatibility
    categories = sorted(list(set([v["Category"] for v in CATALOG.values()])))
    selected_category = st.selectbox("Category", categories)
    
    filtered_items = [k for k, v in CATALOG.items() if v["Category"] == selected_category]
    selected_item = st.selectbox("Select Item", filtered_items)
    
    qty = st.number_input("Quantity", min_value=1, value=100, step=10)
    
    if st.button("➕ Add to Bid", type="primary", use_container_width=True):
            item_data = CATALOG[selected_item]
            st.session_state.bid_items.append({
                "Item": selected_item,
                "Category": item_data["Category"],
                "UOM": item_data["UOM"],
                "Quantity": qty,
                "Labor/U": item_data["Labor"],
                "Equip/U": item_data["Equip"],
                "Mat/U": item_data["Material"],
                "Total/U": item_data["Labor"] + item_data["Equip"] + item_data["Material"]
            })
            st.rerun()

    # Current Bid Section
    st.divider()
    st.subheader(f"2. Current Bid: {project_name}")

    if st.session_state.bid_items:
        df = pd.DataFrame(st.session_state.bid_items)
        
        # Calculate totals
        df["Total Labor"] = df["Quantity"] * df["Labor/U"]
        df["Total Equip"] = df["Quantity"] * df["Equip/U"]
        df["Total Mat"] = df["Quantity"] * df["Mat/U"]
        df["Direct Cost"] = df["Quantity"] * df["Total/U"]
        
        # Display formatted table
        display_df = df[["Item", "Quantity", "UOM", "Total/U", "Direct Cost"]].copy()
        display_df["Total/U"] = display_df["Total/U"].apply(lambda x: f"${x:,.2f}")
        display_df["Direct Cost"] = display_df["Direct Cost"].apply(lambda x: f"${x:,.2f}")
        
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
        # Summary Metrics
        total_labor = df["Total Labor"].sum()
        total_equip = df["Total Equip"].sum()
        total_mat = df["Total Mat"].sum()
        total_direct = df["Direct Cost"].sum()
        
        total_markup = total_direct * (markup_pct / 100.0)
        final_bid = total_direct + total_markup
        
        st.subheader("3. Project Summary")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Direct Cost", f"${total_direct:,.2f}")
        m2.metric(f"Markup ({markup_pct}%)", f"${total_markup:,.2f}")
        m3.metric("Final Bid Price", f"${final_bid:,.2f}")
        
        st.markdown("### Budget Breakdown")
        b1, b2, b3 = st.columns(3)
        b1.metric("Labor Budget", f"${total_labor:,.2f}")
        b2.metric("Equipment Budget", f"${total_equip:,.2f}")
        b3.metric("Material Budget", f"${total_mat:,.2f}")
        
        if st.button("🗑️ Clear Bid"):
            st.session_state.bid_items = []
            st.rerun()
    else:
        st.info("Your bid is empty. Add items from the catalog above to get started.")

