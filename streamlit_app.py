import streamlit as st
import pandas as pd
import os

import requests
from requests.auth import HTTPBasicAuth
import urllib.parse


import base64
from typing import Tuple
from typing import List, TypedDict

from datetime import datetime, timedelta


class GetUsersResponse(TypedDict):
    user_id: str
    user_name: str
    email: str

REDIRECT_URI = "http://localhost:8501"  # Update this to your actual redirect URI
AUTH_URL = "https://zoom.us/oauth/authorize"
TOKEN_URL = "https://zoom.us/oauth/token"

ZOOM_API_V2_BASE_URL = "https://api.zoom.us/v2/"
ZOOM_TOKEN_ENDPOINT = "https://zoom.us/oauth/token"

def debugOutput(msg,debugLevel=0):
    if debugLevel > 0:
        print(msg)

def get_acceess_token(client_id: str, client_secret: str, acct_id: str) -> Tuple[str, int]:
    data = {
        "grant_type": "account_credentials",
        "account_id": acct_id,
    }

    encoded_auth_header = base64.b64encode(
        f"{client_id}:{client_secret}".encode("utf-8")
    ).decode("utf-8")

    headers = {"Host": "zoom.us", "Authorization": f"Basic {encoded_auth_header}"}

    response = requests.post(ZOOM_TOKEN_ENDPOINT, data=data, headers=headers)
    parsed_reponse = response.json()

    access_token = parsed_reponse["access_token"]
    expiry = parsed_reponse["expires_in"]

    return access_token, expiry

def get_zoom_recordings(access_token, user_id,months_ago=0, day_range=30):
    base_url = f"https://api.zoom.us/v2/users/{user_id}/recordings"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    start_days_ago=months_ago*30+day_range
    end_days_ago=months_ago*30

    # Set the "from" date as far back as possible (Zoom retains data up to 6 months for free accounts)
    from_date = (datetime.now() - timedelta(days=start_days_ago)).strftime("%Y-%m-%d")
    to_date = (datetime.now() - timedelta(days=end_days_ago)).strftime("%Y-%m-%d")
    next_page_token = None  # For pagination
    all_recordings = []  # To store all recordings

    while True:
        params = {
            "from": from_date,
            "to": to_date,
            "page_size": 300  # Maximum number of results per page
        }

        # If there's a next page token, include it in the request
        if next_page_token:
            params["next_page_token"] = next_page_token

        response = requests.get(base_url, headers=headers, params=params)

        # Log request and response details for debugging
        #debugOutput("### Zoom Recordings Request")
        debugOutput(f"URL: {response.url}")
        #debugOutput(f"Headers: {headers}")
        #debugOutput(f"Response Status Code: {response.status_code}")
        debugOutput(f"Response Text: {response.text}")

        if response.status_code == 200:
            data = response.json()
            all_recordings.extend(data.get("meetings", []))  # Add the recordings from this page

            # Check if there's another page of data
            next_page_token = data.get("next_page_token")
            if not next_page_token:
                break  # No more pages, exit loop
            debugOutput(f"Next page token: {next_page_token} for {user_id}")
        else:
            debugOutput(f"ERROR ERROR ERROR!!\n\nFailed to fetch recordings: {response.status_code}")
            return None

    return all_recordings 

def get_users(access_token) -> List[GetUsersResponse]:
    user_details: List[GetUsersResponse] = []
    list_users_url = ZOOM_API_V2_BASE_URL + "users"

    zoom_auth_header = {"Authorization": f"Bearer {access_token}"}

    params = {
        "page_size": 100,
    }

    response = requests.get(list_users_url, params=params, headers=zoom_auth_header)
    #debugOutput(f"Response JSON: {response.json()}")
    #return response

    # Extract user details from the response
    users = response.json()["users"]

    # Filter licensed users (type = 2)
    for user in users:
        if user["type"] == 2:
            user_id = user["id"]
            user_name = user["display_name"]
            email = user["email"]

            user_details.append(
                {
                    "user_id": user_id,
                    "user_name": user_name,
                    "email": email,
                }
            )

    return user_details

def get_cache_token():
    if 'access_token' not in st.session_state:
        client_id = st.secrets["CLIENT_ID"]
        client_secret = st.secrets["CLIENT_SECRET"]
        acct_id = st.secrets["ACCT_ID"]
        (access_token,expiry)=get_acceess_token(client_id, client_secret, acct_id)
        st.session_state['access_token'] = access_token
    return st.session_state['access_token']

def refresh_recordings():
    access_token=get_cache_token()
    user_details=get_users(access_token)
    total_recordings=[]
    for user_detail in user_details:
        print(f"Getting recordings for {user_detail['user_id']}")
        user_id=user_detail['user_id']
        user_name=user_detail['user_name']
        user_email=user_detail['email']
        month_count=18
        for month in range(month_count):
            print(f"Getting recordings for {user_detail['user_id']} for month {month} of {month_count}")
            recordings=get_zoom_recordings(access_token, user_id,month,30)
            for r in recordings:
                r["MB"]=round(r["total_size"]/(1024*1024))
                r["user_name"]=user_name
                r["user_email"]=user_email
            
                r.pop('recording_files') if 'recording_files' in r else None
                r.pop('meetings') if 'meetings' in r else None
                r.pop('play_url') if 'play_url' in r else None
                r.pop('download_url') if 'download_url' in r else None
                r.pop('meeting_id') if 'meeting_id' in r else None
                r.pop('id') if 'id' in r else None
                r.pop('uuid') if 'uuid' in r else None
                r.pop('share_url') if 'share_url' in r else None
                r.pop('recording_play_passcode') if 'recording_play_passcode' in r else None
                r.pop('account_id') if 'account_id' in r else None
                r.pop('recording_code') if 'recording_code' in r else None
                r.pop('timezone') if 'timezone' in r else None
                r.pop('type') if 'type' in r else None
                r.pop('total_size') if 'total_size' in r else None


                total_recordings.append(r)
    st.session_state['recordings'] = total_recordings
    return st.session_state['recordings']

def get_cache_recordings():
    if os.path.exists("zoom_recordings.csv"):
        print("Reading from file")
        df=pd.read_csv("zoom_recordings.csv")
        st.session_state['recordings'] = df.to_dict(orient='records')
    if 'recordings' not in st.session_state:
        refresh_recordings()
    return st.session_state['recordings']

def one_run():
    print("\n Starting a new run")
    #st.write("\nStarting a new run")
    if st.sidebar.button("Refresh Token"):
        client_id = st.secrets["CLIENT_ID"]
        client_secret = st.secrets["CLIENT_SECRET"]
        acct_id = st.secrets["ACCT_ID"]
        (access_token,expiry)=get_acceess_token(client_id, client_secret, acct_id)
        st.session_state['access_token'] = access_token
    access_token=get_cache_token()
    print("Got access token")
    #st.write("Got access token")
    if st.sidebar.button("Refresh Recordings"):
        print("Refreshing recordings")
        #st.write("Refreshing recordings")
        refresh_recordings()
        print("Finished refreshing recordings")
        #st.write("Finished refreshing recordings")
    print("Getting recordings")
    #st.write("Getting recordings")
    recordings=get_cache_recordings()
    print("Got recordings")
    df=pd.DataFrame(recordings)
    df.to_csv("zoom_recordings.csv",index=False)
    print("Saved file")
    #st.write("Saved file")

    # Show the total size of recordings by user name
    st.title("Summary")
    st.write(f"Total recordings: {len(df)}, total size: {df['MB'].sum()/1024:.1f} GB")
    st.write(df.groupby("user_name")["MB"].sum())
    st.title("Details")
    st.dataframe(df,column_order=("user_name","user_email","topic","start_time","duration","MB"),hide_index=True)
    if st.sidebar.button("Refresh display"):
        st.sidebar.write("Refreshed display")
    print("Done with run")
    #st.write("Done with run")



st.sidebar.title("🎈 Zoom Size")
one_run()
