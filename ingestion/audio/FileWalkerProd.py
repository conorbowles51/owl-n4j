# Import module
from datetime import datetime
import os

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

from striprtf.striprtf import rtf_to_text


# es = Elasticsearch("http://sirenadmin:password@localhost:9220")
es = Elasticsearch("http://localhost:9200")

home_dir = "/home/neil/PycharmProjects/NarcoCase"
# home_dir = "/home/neibyr/NarcoCase"


# # set up NLP
# nlp = spacy.load("en_core_web_lg")
# nlp.add_pipe("gliner_spacy", config={"labels": ["name", "person", "organization", "email", "phone", "weapon", "vehicle", "currency", "amount", "location"]})
#
# doc = nlp("I don't know. There is nothing around there. I'm going to neil talk to the priest Serbia. Where are you going? Who's the priest? No, no. They had stolen the coffee I told you about. They were the muckers who were in front of us. And... and let's see if they could... They were the muckers who were in front of us. And let's see if they could... They were the muckers who were in front of us. They were the muckers who were in front of us. And let's see if, like... If you said someone or they could... Ah... They could've been... They could've been woman, or something like that. I've been� Smoothie with a thousand dollars. You've got that for real? Yes. They're the muckers who were in front of us. They're the muckers. They were the roghters. They're the muckers. The muckers that grows there. How do we know who they are? No, no, who knows, man, just the ones in front of you. Do you remember where you said you were going to do me the favor? Yes. No, there they gave me to the gentleman. They were talking to me that, please, because they live the fucking dollar robbing $ 3,000. Okay, well, give us your data, tell me exactly where it is and how and please, where did you put it? Do you want me to ask you and I'll talk to you, are you talking because your phone is off? Yes, it's off, I'll talk to him later. Okay, I'll talk to you then.")

wiretaps = []
# for ent in doc.ents:
#     print(ent.text, ent.label_)

# Assign directory
directory = r"./01_Bates_210-237-1858-6-16-07-thru-7-14-07"
directories = [ "003"]

def strip_names(name_string):
    name_tokens = name_string.split(" ")
    print (name_tokens)
    for name in name_tokens:
        print (name)
        if name != "":
            return name
    return None

# Iterate over files in directory
for directory in directories:
    dir =  r'./Bates/{directory}'.format(directory=directory)
    # print ("DIR", directory, dir)
    for path, folders, files in os.walk(dir):
        # print ("LOCATION AND FILES: ", folders, dir)

        # List contain of folder
        for folder_name in folders:
            # print("Content of " + folder_name + "out of " + str(folders))
            # Logic to transcribe, translate, and gather meta-data for each wiretap
            '''
            1- Transcription in Spanish and it's english translation.**
            2- Metadata Associated to the file.*
            3- The relevant origination data that will help us map out who the players are/timeline.*
            4- The Gov's interpretation of the call.*
            5- A field of the people involved in the call.***
            6- A field for us to be able to determine if relevant or not.
            7- A field for the Investigator's notes & observations
            8- An automatic field that fills in who was or the investigators that worked on this entry.'''

            # From audio
            spanish_transcription = ""
            english_transcription = ""

            # From Govt interpretation syn.rtf files
            prosecutors_interpretation = ""

            # From .sri metadata file
            time_of_call = None
            contact_id = 0
            input_line_id = 0

            # Persons involved
            person1 = None
            person2 = None
            persons = [person1, person2]

            # Data location reference points
            bates_folder = directory
            wiretap_folder_number = folder_name
            siren_id = "Bates_" + directory + "_" + folder_name
            # print ("siren id: ", siren_id)

            # Siren User fields
            relevant = "n/a"
            investigator_notes = "not yet reviewed"
            investigated_by = "not yet investigated"

            for filenames in os.scandir(path+"/"+folder_name):
                # print ("Files in Wiretap ", filenames.name)
                file_path_to_open = path + "/" + folder_name + "/" + filenames.name

                if filenames.name.endswith(".sri"):
                    with open(file_path_to_open, 'r') as file:
                        lines = file.readlines()
                        # print ("LINES: ", lines)
                        time_of_call_string = lines[2].split("=")[1].rsplit(" ", 1)[0]
                        time_of_call = datetime.strptime(time_of_call_string, "%Y-%m-%d %H:%M:%S")
                        # print (time_of_call)

                        contact_id = lines[5].split("=")[len(lines[5].split("="))-1]
                        # print (contact_id)

                        input_line_id = lines[1].split("=")[len(lines[1].split("=")) - 1].split("\n")[0]
                        # print(input_line_id)

                if filenames.name.endswith(".rtf"):
                    # print ("rts")
                    with open(file_path_to_open, 'r') as file:
                        content = file.read()
                        text = rtf_to_text(content)
                        prosecutors_interpretation = text
                        # print(prosecutors_interpretation)
                        persons_involved = text.split("\n")
                        for lines in persons_involved:
                            if " TO " in lines:
                                # print("persons", lines)
                                name1 = strip_names(lines.split(" TO ")[0])
                                name2 = strip_names(lines.split(" TO ")[1])
                                if name1 is not None and name2 is not None:
                                    person1 = {"name": name1, "calls":[{"call": lines, "context": lines.split(" TO ")[0].split(" "), "context_string": prosecutors_interpretation, "made_call": siren_id, "received_call": "na"}]}
                                    person2 = {"name": name2, "calls":[{"call": lines,"context": lines.split(" TO ")[1].split(" "), "context_string": prosecutors_interpretation, "made_call": "na", "received_call": siren_id}]}
                                print ("p1", person1)
                                print("p2", person2)
                                break


                if filenames.name.endswith((".WAV", ".wav", ".mp3", ".MP3")):
                    print ("audio", file_path_to_open)
                    os.system("python3 audiototext.py " + file_path_to_open + " --task transcribe --language Spanish --output_format txt --output_dir " + home_dir + "/wiretap_text/spanish --skip-install")
                    with open(home_dir + "/wiretap_text/spanish/" + filenames.name.split(".")[0] + ".txt", 'r') as file:
                        spanish_transcription = file.read()
                    os.system("python3 audiototext.py " + file_path_to_open + " --task translate --language Spanish --output_format txt --output_dir " + home_dir + "/wiretap_text/english --skip-install")
                    with open(home_dir + "/wiretap_text/english/" + filenames.name.split(".")[0] + ".txt", 'r') as file:
                        english_transcription = file.read()


            # List content from folder
            wiretap = {
                "spanish_transcription": spanish_transcription,
                "english_transcription": english_transcription,
                "prosecutors_interpretation": prosecutors_interpretation,
                "time_of_call": time_of_call,
                "contact_id": contact_id,
                "input_line_id": input_line_id,
                "bates_folder": bates_folder,
                "wiretap_folder_number": wiretap_folder_number,
                "relevant": relevant,
                "investigator_notes": investigator_notes,
                "investigated_by": investigated_by
            }
            # print ("WIRETAP", wiretap)
            wiretaps.append(wiretap)

            push_wiretaps = [{
                "_index": "wiretaps-date-profile",
                "_id": siren_id,
                "_source": {
                    "spanish_transcription": spanish_transcription,
                    "english_transcription": english_transcription,
                    "prosecutors_interpretation": prosecutors_interpretation,
                    "time_of_call": time_of_call,
                    "contact_id": contact_id,
                    "input_line_id": input_line_id,
                    "bates_folder": bates_folder,
                    "wiretap_folder_number": wiretap_folder_number,
                    "relevant": relevant,
                    "investigator_notes": investigator_notes,
                    "investigated_by": investigated_by

                }
            }
                for j in range(0, len(wiretaps))
            ]


            # print ("p",persons)
            bulk(es, push_wiretaps)


            if person1 is not None and person2 is not None:
                if es.indices.exists(index="persons"):
                    check_person1 = es.search(index="persons", query={"match": {"_id": person1["name"]}})
                    print ("chk", check_person1)
                    p1 = {}
                    p1["name"] = person1["name"]
                    try:
                        p1["calls"] = check_person1["hits"]["hits"][0]["_source"]["calls"]
                        print ("calls", p1["calls"])
                    except:
                        p1["calls"] = []
                    p1["calls"] += person1["calls"]

                    check_person2 = es.search(index="persons", query={"match": {"_id": person2["name"]}})
                    p2 = {}
                    p2["name"] = person2["name"]
                    try:
                        p2["calls"] = check_person2["hits"]["hits"][0]["_source"]["calls"]
                    except:
                        p2["calls"] = []
                    p2["calls"] += person2["calls"]
                    persons = [p1, p2]
                else:
                    persons=[person1,person2]

                push_persons = [{
                    "_index": "persons",
                    "_id": persons[j]["name"],
                    "_source": {
                        "name": persons[j]["name"],
                        "calls": persons[j]["calls"]
                        # "call":  persons[j]["call"],
                        # "context": persons[j]["context"],
                        # "context_string": persons[j]["context_string"],
                        # "received_call": persons[j]["received_call"],
                        # "made_call": persons[j]["made_call"]
                    }
                }
                    for j in range(0, len(persons))
                ]
                # if p1["name"] != "" and p2["name"] != "":
                bulk(es, push_persons)

            wiretaps = []

