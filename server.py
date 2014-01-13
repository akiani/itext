#!/usr/bin/env python2.7

'''
Created on Jan 11, 2014

@author: amir
'''

from flask import Flask, render_template, url_for, request, redirect, url_for
from werkzeug import secure_filename
import os, uuid, json, sqlite3, re, sys, traceback, operator

app = Flask(__name__, static_folder='templates')

UPLOAD_FOLDER = 'uploads'
SMS_DB_SHA1 = '3d0d7e5fb2ce288813306e4d4636395e047a3d28'
ALLOWED_EXTENSIONS = set(['*'])

STOP_WORDS = set(["i","me","my","myself","we","us","our","ours","ourselves","you","your","yours",
                  "yourself","yourselves","he","him","his","himself","she","her","hers","herself","it",
                  "its","itself","they","them","their","theirs","themselves","what","which","who","whom","whose",
                  "this","that","these","those","am","is","are","was","were","be","been","being","have","has",
                  "had","having","do","does","did","doing","will","would","should","can","could","ought",
                  "i'm","you're","he's","she's","it's","we're","they're","i've","you've","we've","they've",
                  "i'd","you'd","he'd","she'd","we'd","they'd","i'll","you'll","he'll","she'll","we'll",
                  "they'll","isn't","aren't","wasn't","weren't","hasn't","haven't","hadn't","doesn't","don't",
                  "didn't","won't","wouldn't","shan't","shouldn't","can't","cannot","couldn't","mustn't",
                  "let's","that's","who's","what's","here's","there's","when's","where's","why's","how's",
                  "a","an","the","and","but","if","or","because","as","until","while","of","at","by","for",
                  "with","about","against","between","into","through","during","before","after","above",
                  "below","to","from","up","upon","down","in","out","on","off","over","under","again","further","then","once","here",
                  "there","when","where","why","how","all","any","both","each","few","more","most",
                  "other","some","such","no","nor","not","only","own","same","so","than","too","very","say","says","said","shall"])


def which_db_version(cursor):
    """
    Return version of DB schema as string.

    Return '5', if iOS 5.
    Return '6', if iOS 6.

    """
    query = "select count(*) from sqlite_master where name = 'handle'"
    cursor.execute(query)
    count = cursor.fetchone()[0]
    if count == 1:
        db_version = '6'
    else:
        db_version = '5'
    return db_version

def strip(phone):
    """Remove all non-numeric digits in phone string."""
    if phone:
        return re.sub('[^\d]', '', phone)
    
def build_msg_query(numbers, emails):
    """
    Build the query for SMS and iMessage messages.
    
    If `numbers` or `emails` is not None, that means we're querying for a
    subset of messages. Phone number is in `address` field for SMS messages,
    and in `madrid_handle` for iMessage. Email is only in `madrid_handle`.
    
    Because of inconsistently formatted phone numbers, we run both passed-in
    numbers and numbers in DB through trunc() before comparing them.
    
    If `numbers` is None, then we select all messages.
    
    Returns: query (string), params (tuple)
    """
    query = """
SELECT 
    rowid, 
    date, 
    address, 
    text, 
    flags, 
    group_id, 
    madrid_handle, 
    madrid_flags,
    madrid_error,
    is_madrid, 
    madrid_date_read,
    madrid_date_delivered
FROM message """
    # Build up the where clause, if limiting query by phone.
    params = []
    or_clauses = []
    if numbers:
        for n in numbers:
            or_clauses.append("TRUNC(address) = ?")
            or_clauses.append("TRUNC(madrid_handle) = ?")
            params.extend([trunc(n), trunc(n)])
    if emails:
        for e in emails:
            or_clauses.append("madrid_handle = ?")
            params.append(e)
    if or_clauses:
        where = "\nWHERE " + "\nOR ".join(or_clauses)
        query = query + where
    query = query + "\nORDER by rowid"
    return query, tuple(params)

def build_msg_query_ios6(numbers=None, emails=None):
    """
    Build the query for SMS and iMessage messages for iOS6 DB.

    If `numbers` or `emails` is not None, that means we're querying for a
    subset of messages. Both phone number and email is stored in the `id`
    field of the handle table.

    If `numbers` is None, then we select all messages.

    Returns: query (string), params (tuple)
    """
    query = """
SELECT
    m.rowid,
    m.date,
    m.is_from_me,
    h.id,
    m.text
FROM
    message m,
    handle h
WHERE
    m.handle_id = h.rowid"""
    # Build up the where clause, if limiting query by phone and/or email.
    params = []
    or_clauses = []
    if numbers:
        for n in numbers:
            or_clauses.append("TRUNC(h.id) = ?")
            params.append(trunc(n))
    if emails:
        for e in emails:
            or_clauses.append("h.id = ?")
            params.append(e)
    if or_clauses:
        where = "\nAND\n(" + "\nOR ".join(or_clauses) + ")"
        query = query + where
    query = query + "\nORDER by m.rowid"
    return query, tuple(params)
    
def trunc(phone):
    """Strip phone, then truncate it.  Return last 10 digits"""
    if phone:
        ph = strip(phone)
        return ph[-10:]

def skip_imessage(row):
    """
    Return True, if iMessage row should be skipped.
    
    I whitelist madrid_flags values that I understand:
    
         36869   Sent from iPhone to SINGLE PERSON (address)
        102405   Sent to SINGLE PERSON (text contains email, phone, or url)
         12289   Received by iPhone
         77825   Received (text contains email, phone, or url)
    
    Don't handle iMessage Group chats:
        
         32773   Sent from iPhone to GROUP
         98309   Sent to GROUP (text contains email, phone or url)
     
    See wiki page on FLAGS fields for more details:
        
    """
    flags_group_msgs = (32773, 98309)
    flags_whitelist = (36869, 102405, 12289, 77825)
    retval = False
    if row['madrid_error'] != 0:
        retval = True
    elif row['madrid_flags'] in flags_group_msgs:
        retval = True
    elif row['madrid_flags'] not in flags_whitelist:
        retval = True
    elif not row['madrid_handle']:
        retval = True
    elif not row['text']:
        retval = True
    return retval

def clean_text_msg(txt):
    """
    Return cleaned-up text message.

        1. Replace None with ''.
        2. Replace carriage returns (sent by some phones) with '\n'.

    """
    txt = txt or ''
    return txt.replace("\015", "\n")

def skip_sms(row):
    """Return True, if sms row should be skipped."""
    retval = False
    if row['flags'] not in (2, 3):
        retval = True
    elif not row['address']:
        retval = True
    elif not row['text']:
        retval = True
    return retval


def get_messages(cursor, query, params):
    cursor.execute(query, params)

    dictionary = {}
    for row in cursor:
        if row['is_madrid'] == 1:
            if skip_imessage(row): continue
        else:
            if skip_sms(row): continue
        add_to_dict(dictionary,clean_text_msg(row['text']))
    return dictionary

def add_to_dict(dictionary, message):
    message = message.replace(".","")
    message = message.replace(",","")
    words = message.split(" ")
    for word_ in words:
        word = word_.lower()

        if word != "" and word not in STOP_WORDS and len(word) > 1:
            if word in dictionary:
                dictionary[word] = dictionary[word] + 1
            else:
                dictionary[word] = 1
        

def get_messages_ios6(cursor, query, params):
    cursor.execute(query, params)
    dictionary = {}
    for row in cursor:
        add_to_dict(dictionary,clean_text_msg(row['text']))
    return dictionary


@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files['file']
    if file:
        filename = secure_filename(file.filename)
        if filename == SMS_DB_SHA1 :
            uuid_str = str(uuid.uuid1())
            file.save(os.path.join(UPLOAD_FOLDER, uuid_str))
            return json.dumps({"success": uuid_str})
        else:
            return json.dumps({"error": "Filename doesn't match SMS DB (" + SMS_DB_SHA1 + ")"})



@app.route('/process', methods=['GET'])
def process():
    db_id = request.args.get('db', '')
    wordcount = {}
    if db_id:
        try:
            print "Processing " + db_id
            
            conn = sqlite3.connect(os.path.join(UPLOAD_FOLDER, db_id))
            conn.row_factory = sqlite3.Row
            conn.create_function("TRUNC", 1, trunc)
            cur = conn.cursor()

            ios_db_version = which_db_version(cur)
            if ios_db_version == '5':
                query, params = build_msg_query()
                wordcount = get_messages(cur, query, params)
            elif ios_db_version == '6':
                query, params = build_msg_query_ios6()
                wordcount = get_messages_ios6(cur, query, params)
            sorted_list = sorted(wordcount.iteritems(), key=operator.itemgetter(1), reverse=True)
            return json.dumps(sorted_list[0:200])
        
        except:
            print '-'*60
            traceback.print_exc(file=sys.stdout)
            print '-'*60
            
        finally:
            if conn:
                conn.close()
        
        
@app.route('/status', methods=['GET'])
def check_status():
    db_id = request.args.get('db', '')
    if db_id:
        os.path.isfile(os.path.join(UPLOAD_FOLDER, db_id))
    return "Missing db parameter." , 404


@app.route("/", methods=['GET'])
def index():
    return render_template('index.html')


if __name__ == "__main__":
    app.run(debug=True)