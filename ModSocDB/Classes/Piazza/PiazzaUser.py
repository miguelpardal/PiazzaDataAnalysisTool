# This file is covered by the LICENSE file in the root of this project.
# @license <https://github.com/ArgLab/PiazzaDataAnalysisTool/blob/master/LICENSE>
#!/usr/bin/env python
"""
PiazzaUser.py
:Author: Collin Lynch
:Date: 09/29/2014

The PiazzaUser class defines users of the Piazza system and provides for access to the users themselves.  These will be generated from the raw piazza users and differ chiefly in the existence of the split names.
"""

# -------------------------------------------
# imports.
# ===========================================
import string

from ming import schema
from ming.odm import FieldProperty, ForeignIdProperty, RelationProperty
from ming.odm.declarative import MappedClass

# Load the shared session objects and library classes.
# -----------------------------------------------------
import ModSocDB
from ModSocDB import NLP
from ModSocDB.Classes import User as UserMod

# Split libraries.
# --------------------------------------------------
import name_tools


# ===========================================
class PiazzaUser(MappedClass):
    """
    The PiazzaUser class represents a wrapper for the user records that
    were pulled from the piazza data in the form of the RawPiazzaUser
    instances.  They will be generated by code in the RawPiazzaUser
    module and would then generate the first and last names and perform
    other relevant features.

    Access to the fields will be provided later on as needed and
    anonymization when it happens will be done on this object.

    The user contains the following fields:
  
    Collection: piazza_users


    Relations:
    ---------------------------------------------------
    * Dataset: Link to the associated Dataset.
    * PiazzaContent_GoodTags: Relationship with good tags by this user.
    * PiazzaContent_HistoryEntries: Relationship with edited history elements.
    * PiazzaContent_ChangeLogs: ChangeLog Entries for the PiazzaContent.
    * PiazzaContent_Children: Children authored.
    * PiazzaContent_Child_Endorsements: Endorsements of child posts.
    * PiazzaContent_Child_HistoryEntries: History of children.
    * PiazzaContent_Child_Subchildren: Subchildren authored by this user.


    Fields:
    -------------------------------------------------------------
    * Course_ID: ID of the associated Dataset.
    * _id: Mongodb object ID (unique).
    * user_id: (string) Piazza unique user ID.  
    * answers: (int) Count of answers given to questions.
    * posts: (int) Count of posts made.
    * views: (int) Count of views made.  
    * asks: (int) Count of asks made.  
    * name: (string) Student real name or anonymized name.
    * days: (int) Days active or logged in?
    * email: (string) User's email address (is in standard form so can be split.)
    * first_name: (string) first name of student extracted from name field.
    * middle_name: (string) middle name of student extracted from name field.
    * last_name: (string) last name of student extracted from name field.
    """

    # ---------------------------------------------
    # Mongometa information.
    # =============================================
    class __mongometa__:
        session = ModSocDB.Session
        name = "piazza_users"


    # ---------------------------------------------
    # Link Information
    # =============================================
    
    # Relationship with good tags by this user.
    PiazzaContent_GoodTags = RelationProperty("PiazzaContent_TagGood")

    # Relationship with edited history elements.
    PiazzaContent_HistoryEntries = RelationProperty("PiazzaContent_History")

    # ChangeLog Entries for the PiazzaContent.
    PiazzaContent_ChangeLogs = RelationProperty("PiazzaContent_ChangeLog")

    # Children authored.
    PiazzaContent_Children = RelationProperty("PiazzaContent_Child")
    
    # Endorsements of child posts.
    PiazzaContent_Child_Endorsements = RelationProperty("PiazzaContent_Child_Endorsement")

    # History of children.
    PiazzaContent_Child_HistoryEntries = RelationProperty("PiazzaContent_Child_History")

    # Subchildren authored by this user.
    PiazzaContent_Child_Subchildren = RelationProperty("PiazzaContent_Child_Subchild")

    # ID of the main user to which this is linked (updated on MigrateRawContent).
    CentralUser_ID = ForeignIdProperty("User")
    CentralUser    = RelationProperty("User")
    
    # Link to the associated Dataset (updated on MigrateRawContent)
    Course_ID = ForeignIdProperty('Dataset')
    Course    = RelationProperty('Dataset')

    # ---------------------------------------------
    # Original Fields.
    #
    # These fields are part of the original Piazza data.
    # as downloaded in the fields.
    # =============================================

    # Mongodb object ID (unique).
    _id     = FieldProperty(schema.ObjectId)

    # Piazza unique user ID.  
    user_id = FieldProperty(str)    
    
    # Count of answers given to questions.
    answers = FieldProperty(int)

    # Count of posts made.
    posts   = FieldProperty(int)

    # Count of views made.  
    views   = FieldProperty(int)

    # Count of asks made.  
    asks    = FieldProperty(int)

    # Student real name or anonymized name.
    name      = FieldProperty(str)

    # Days active or logged in?
    days    = FieldProperty(int)

    # User's email address (is in standard form so can be split.)
    email   = FieldProperty(str)

    # A note that may indicate specific caveats about this user ID.
    note    = FieldProperty(str, required=False, if_missing=None)

    # ---------------------------------------------
    # Added Fields.
    #
    # These are split fields or other resolution fields that
    # will be added to the instance by the migration fields
    # below.  
    # =============================================

    # Split field for individual names.
    first_name  = FieldProperty(str)
    middle_name = FieldProperty(str)
    last_name   = FieldProperty(str)


    # ======================================================================
    # Duplicate Methods.
    #
    # Remove Duplace elements from the database.  
    # ======================================================================

    @staticmethod
    def removeDuplicateUsers(DatasetID):
        """
        Remove duplicate users from the dataset.
        """
        UserIDs = set(collectAllPiazzaIDs())
        for ID in UserIDs:
            Users = collectUsersByPiazzaID(ID)
            if (len(Users) > 1):
                # print "%s %d" % (ID, len(Users))
                for U in Users[1:]:
                    U.delete()
                    
        ModSocDB.Session.flush()
        

    # ======================================================================
    # Migration Function.
    #
    # Migrate or update the initial raw format with one that adds in the
    # split name fields and other data.  
    # ======================================================================

    @staticmethod
    def migrateRawContent(DatasetID):
        """
        This is a static method that will extract and iterate over
        the raw user content to generate the additional fields that
        will be used for later evaluation.

        At the same time this will reevaluate the name fields.  If the
        name field is the empty string then it will be set to None. 

        It will also establish a link with an appropriate User instance
        in the database or, if none is present, it will create one.
        """
        Results = []
        RawUserList = PiazzaUser.query.find()
        for PUser in RawUserList:

            # Set the dataset ID.
            PUser.Course_ID = DatasetID

            # If the name field is "" then set it to None so
            # that the absence of a name is clear.  If not then
            # set the split name fields accordingly.  We will
            # then search for a matching user by name for merging.
            #
            # If none is found then we will make a user.  For the sake
            # of clarity we will treat users with None as the name as
            # unique and will not search for them.
            if (PUser.email == "") or (PUser.email == None):
                PUser.email = None
                CUser = None
            else:                
                CUser = UserMod.findUserByEmail(PUser.email)

            # print "CUser Found: %s" % (CUser) 
            
            if (CUser == None):
                PUser.makeSplitNameFields()
                first_name = PUser.first_name.title() if PUser.first_name else ""
                last_name = PUser.last_name.title() if PUser.last_name else ""
                CUser = UserMod.findUserByFirstLast(first_name,last_name)
                
                # print "CUser Found: %s" % (CUser)                                
                
                if (CUser == None):
                    CUser = UserMod.User.makeNewUser(
                        DatasetID=DatasetID,
                        Name=PUser.name.title(),
                        Email=PUser.email,
                        FirstName=first_name,
                        MiddleName=PUser.middle_name,
                        LastName=last_name,
                        PiazzaUserID=PUser._id)
                    # print "CUser Made: %s" % (CUser)
                else:
                    CUser.piazza_alt_email = PUser.email
                # ModSocDB.Session.flush()
                                
            # And now set the appropriate link information to the
            # central user.
            PUser.CentralUser_ID = CUser._id 
            CUser.PiazzaUser_ID = PUser._id
            CUser.PiazzaID = PUser.user_id
            ModSocDB.Session.flush()         
            Results.append(CUser)
            
        ModSocDB.Session.flush()
        return Results
    

    # Add pushCentralAuthor(self) which goes over linked items and sets the
    # CentralAuthor_ID to be the same as the local central author.  
    

    def makeSplitNameFields(self):
        """
        Split the user name into personal and family names so that
        those can be used for searching in the text.  This uses
        the name_tools library to segment the name into the
        standard blocks (Honorific, Personal Name, Family Name,
        Modifier).  It will then split the personal name on
        whitespace to get the first name.  
        """
        # print self.name
        Dict = NLP.makeSplitNameDict(self.name)
        
        self.first_name  = Dict["FirstName"]
        self.middle_name = Dict["MiddleName"]
        self.last_name   = Dict["LastName"]

        # print self
        return Dict



    # ---------------------------------------------
    # Simple Accessors/Settors
    # =============================================

    def getUserID(self):
        """
        Get the Piazza User ID set in the system.
        """
        return self.user_id

    
    def setUserID(self, NewUID):
        """
        Set the user_id field.
        """
        self.user_id = NewUID
        

    def getName(self):
        """
        Get the User name.
        """
        return self.name

    
    def setName(self, NewName):
        """
        Set the user name.
        """
        self.name = NewName


    def getFirstName(self):
        """
        Get the first_name value.
        """
        return self.first_name


    def setFirstName(self, NewName):
        """
        Set the first_name field.
        """
        self.first_name = NewName


    def getMiddleName(self):
        """
        Get the middle_name value.
        """
        return self.middle_name

    
    def setMiddleName(self, NewName):
        """
        Set the middle_name field.
        """
        self.middle_name = NewName


    def getLastName(self):
        """
        Get the last_name value.
        """
        return self.last_name

    
    def setLastName(self, NewName):
        """
        Set the last_name field.
        """
        self.last_name = NewName


    def getEmail(self):
        """
        Get the email.
        """
        return self.email

    
    def setEmail(self, NewEmail):
        """
        Set the new email.
        """
        self.email = NewEmail 

    # ---------------------------------------------
    # Complex Accessors/Settors
    # =============================================
        
    def getSplitEmail(self):
        """
        If the e-mail is not null split it around the @
        and return the pairs as a 2-tuple.
        """
        Index = self.email.find('@')
        if (Index == -1): return (None, None)
        else: return (self.email[:Index], self.email[Index+1:])

                
    def getSplitName(self):
        """
        This accessor uses the name_tools library to
        get the split name contents as a tuple which
        will then be returned.  It is also used to set
        the standard first-name, middleName, and LastName
        fields above.
        """
        return name_tools.split(self.name)


    @staticmethod
    def overwriteUserData(DatasetID=None, Timeout=False):
        """
        This static method will query for all defined users and will
        overwrite their ID information based upon the information in
        the associated User class instance.

        It is defined here as a static method but will be called
        primarily from the anonymization code after the upstream
        users have been updated.

        Most of the actual work is done by the syncPiazzaAuthorIDs
        method which does the scut work.
        """
        Users = findAllUsers(DatasetID=DatasetID, Timeout=Timeout)
        for U in Users:
            U.user_id = None
            U.syncPiazzaAuthorIDs()
        ModSocDB.Session.flush()
        
        
    def syncPiazzaAuthorIDs(self):
        """
        As part of the anonymization process it is necessary to
        reset the anonymous user ID.  This code will first pull
        the name and ID information from the user instance and 
        will then set the values locally.  

        This code will then iterate over all items that are 
        linked to this user and that have a set author or uid 
        field associated with it.  These will then be reset to 
        the current user ID.  This assumes that the links are 
        already set correctly and that the sole purpose is a 
        brute-force reset of the link code.

        This will also foceably sync user names.  Facebook IDs and
        photos will simply be purged if present.

        NOTE:: This makes no attempt to retain separate facebook IDs
        emails or photos from the good tags or endorsements for later
        use.  
        """
        
        NewID = self.CentralUser.getLocalUserID()
        NewName = self.CentralUser.getName()
        NewFirstName = self.CentralUser.getFirstName()
        NewMiddleName = self.CentralUser.getMiddleName()
        NewLastName = self.CentralUser.getLastName()
        NewEmail = self.CentralUser.getEmail()

        # Set the local information.
        self.setName(NewName)
        self.setFirstName(NewFirstName)
        self.setMiddleName(NewMiddleName)
        self.setLastName(NewLastName)
        self.setEmail(NewEmail)
        
        # The user ID information is on the id field of the tags.
        for Tag in self.PiazzaContent_GoodTags:
            Tag.id          = NewID
            Tag.name        = NewName
            Tag.email       = None
            Tag.photo       = None
            Tag.facebook_id = None
            
        # The UID author info is on the History entries.
        for Hist in self.PiazzaContent_HistoryEntries:
            Hist.uid = NewID

        # ChangeLog Entries for the PiazzaContent.
        for Change in self.PiazzaContent_ChangeLogs:
            Change.uid = NewID
            
        # Children authored.
        for Child in self.PiazzaContent_Children:
            Child.uid = NewID
            Child.id = None
            Child.overwriteUserData()
            
        # Endorsements of child posts.
        for Endorse in self.PiazzaContent_Child_Endorsements:
            Endorse.id          = NewID
            Endorse.name        = NewName
            Endorse.email       = None
            Endorse.photo       = None
            Endorse.facebook_id = None
            
        # History of children.
        for ChildHist in self.PiazzaContent_Child_HistoryEntries:
            ChildHist.id = NewID
            

        # Subchildren authored by this user.
        for Subchild in self.PiazzaContent_Child_Subchildren:
            Subchild.uid = NewID


# -------------------------------------------------
# Utility functions.
# =================================================

def findAllUsers(DatasetID=None, Timeout=True):
    """
    Collect all users from the database.
    """
    if (DatasetID == None): Set =  PiazzaUser.query.find()#(timeout=Timeout)
    else: Set =  PiazzaUser.query.find(Course_ID=DatasetID)#(timeout=Timeout)
    return Set.all()


def collectAllPiazzaIDs(DatasetID=None):
    """
    Collect a list of all PiazzaIDs from the database.
    """
    Set = [U.user_id for U in findAllUsers(DatasetID=DatasetID)]
    return Set


def findUserByID(ID):
    """
    Find the user with the set ID.
    """
    User = PiazzaUser.query.get(_id=ID)
    return User


def findUserByPiazzaID(PiazzaID):
    """
    Find the user with the set Piazza ID.
    """
    User = PiazzaUser.query.get(user_id=PiazzaID)
    return User


def collectUsersByPiazzaID(PiazzaID):
    """
    Find the user with the set Piazza ID.
    """
    Users = PiazzaUser.query.find_by(user_id=PiazzaID).all()
    return Users

def findUserByName(name):
    """
    Find the user with the Piazza Fullname
    """
    User = PiazzaUser.query.get(name = name)
    return User


def countAllUsers():
    """
    Simple query method to count all users in the DB.
    """
    Count = PiazzaUser.query.find().count()
    return Count


def getCentralUserIDByPiazzaID(PiazzaID):
    """
    Find the central user ID associated with the set user ID.  
    Raise an exception if no Piazza User is found.
    """
    # print "Finding User: %s" % (PiazzaID)
    User = findUserByPiazzaID(PiazzaID)
    if (User == None): raise RuntimeError("No matching user found.")
    return User.CentralUser_ID


def getCentralUserIDByPiazzaUserID(ID):
    """
    Find the central user ID associated with the set user ID.  
    Raise an exception if no Piazza User is found.
    """
    # print "Finding User: %s" % (ID)
    User = findUserByID(ID)
    if (User == None): raise RuntimeError("No matching user found.")
    return User.CentralUser_ID
