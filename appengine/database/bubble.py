from google.appengine.ext import db
from datetime import *
from operator import attrgetter

import hashlib

from bo import *
from database.dictionary import *
from database.person import *


class RatingScale(ChangeLogModel):
    name                = db.ReferenceProperty(Dictionary, collection_name='ratingscale_name')

    @property
    def displayname(self):
        return self.name.value

    @property
    def PositiveGradeDefinitions(self):
        return db.Query(GradeDefinition).filter('rating_scale', self).filter('is_positive', True).order('equivalent').fetch(1000)

    @property
    def NegativeGradeDefinitions(self):
        return db.Query(GradeDefinition).filter('rating_scale', self).filter('is_positive', False).order('equivalent').fetch(1000)

    @property
    def GradeDefinitions(self):
        return self.gradedefinitions

    @property
    def gradedefinitions(self):                 # TODO: refactor to GradeDefinitions
        return db.Query(GradeDefinition).filter('rating_scale', self).order('equivalent').fetch(1000)


class BubbleType(ChangeLogModel):
    type                    = db.StringProperty()
    name                    = db.ReferenceProperty(Dictionary, collection_name='bubbletype_name')
    description             = db.ReferenceProperty(Dictionary, collection_name='bubbletype_description')
    allowed_subtypes        = db.StringListProperty()
    maximum_leecher_count   = db.IntegerProperty()
# no two exclusive events should happen to same person at same time
    is_exclusive            = db.BooleanProperty(default=False)
    grade_display_method    = db.StringProperty()

    @property
    def displayname(self):
        if not self.name:
            return '-'

        cache_key = 'bubbletype_dname_' + UserPreferences().current.language + '_' + str(self.key())
        name = Cache().get(cache_key)
        if not name:
            name = StripTags(self.name.value)
            Cache().set(cache_key, name)
        return name

    @property
    def color(self):
        return RandomColor(100,255,100,255,100,255)

    @property
    def allowed_subtypes2(self): #TODO refactor to AllowedSubtypes
        return self.AllowedSubtypes

    @property
    def AllowedSubtypes(self):
        if not self.allowed_subtypes:
            return
        if len(self.allowed_subtypes) == 0:
            return
        CandidateSubtypes = db.Query(BubbleType).fetch(1000)
        AllowedSubtypes = []
        for type in self.allowed_subtypes:
            type_is_valid = False
            for bt in CandidateSubtypes:
                if bt.type == type:
                    AllowedSubtypes.append(bt)
                    type_is_valid = True
                    break
            # If there are non-existing subtypes, remove them and recursively try again
            if not type_is_valid:
                self.allowed_subtypes = RemoveFromList(type, self.allowed_subtypes)
                self.put()
                return self.AllowedSubtypes

        return AllowedSubtypes

    @property
    def AvailableSubtypes(self):
        AvailableSubtypes = db.Query(BubbleType).fetch(1000)
        for type in self.allowed_subtypes:
            for bt in AvailableSubtypes:
                if bt.type == type:
                    AvailableSubtypes.remove(bt)
                    break
        return AvailableSubtypes


    def add_allowed_subtype(self, child_key):
        subtype_to_add = BubbleType.get(child_key)
        self.allowed_subtypes = AddToList(subtype_to_add.type, self.allowed_subtypes)
        self.put()


    def remove_allowed_subtype(self, child_key):
        subtype_to_remove = BubbleType.get(child_key)
        self.allowed_subtypes = RemoveFromList(subtype_to_remove.type, self.allowed_subtypes)
        self.put()


class Bubble(ChangeLogModel):
    name                    = db.ReferenceProperty(Dictionary, collection_name='bubble_name')
    description             = db.ReferenceProperty(Dictionary, collection_name='bubble_description')
    start_datetime          = db.DateTimeProperty()
    end_datetime            = db.DateTimeProperty()
    url                     = db.StringProperty()
    owners                  = db.ListProperty(db.Key)
    editors                 = db.ListProperty(db.Key)
    viewers                 = db.ListProperty(db.Key)
    leechers                = db.ListProperty(db.Key)
    seeders                 = db.ListProperty(db.Key)
    green_persons           = db.ListProperty(db.Key)
    type                    = db.StringProperty()
    #TODO: Check that all bubbles are referenced with respective bubbletype...
    bubble_type             = db.ReferenceProperty(BubbleType, collection_name='bubble_type')
    typed_tags              = db.StringListProperty()
    rating_scale            = db.ReferenceProperty(RatingScale, collection_name='bubble_ratingscale')
    badge                   = db.ReferenceProperty(Dictionary, collection_name='bubble_badge')
    points                  = db.FloatProperty()
    minimum_points          = db.FloatProperty()
    minimum_bubble_count    = db.IntegerProperty()
    maximum_leecher_count   = db.IntegerProperty()
    mandatory_bubbles       = db.ListProperty(db.Key)
    optional_bubbles        = db.ListProperty(db.Key)
    prerequisite_bubbles    = db.ListProperty(db.Key)
    next_in_line            = db.ListProperty(db.Key)
    entities                = db.ListProperty(db.Key)
    state                   = db.StringProperty()
    sort_estonian           = db.StringProperty(default='')
    sort_english            = db.StringProperty(default='')
    search_estonian         = db.StringListProperty()
    search_english          = db.StringListProperty()

    def AutoFix(self):
        self.sort_estonian = StringToSortable(self.name.estonian)
        self.sort_english = StringToSortable(self.name.english)

        self.search_estonian = StringToSearchIndex(self.name.estonian)
        self.search_english = StringToSearchIndex(self.name.english)

        seeders = db.Query(Person, keys_only=True).filter('_is_deleted', False).filter('seeder', self.key()).fetch(1000)
        self.seeders = seeders if seeders else []

        leechers = db.Query(Person, keys_only=True).filter('_is_deleted', False).filter('leecher', self.key()).fetch(1000)
        self.leechers = leechers if leechers else []

        self.put('autofix')

    @property
    def displayname(self):
        if self.name:
            cache_key = 'bubble_dname_' + UserPreferences().current.language + '_' + str(self.key())
            name = Cache().get(cache_key)
            if not name:
                name = StripTags(self.name.value)
                Cache().set(cache_key, name)
            return name
        else:
            return '-'

    def displayname_cache_reset(self):
        cache_key = 'bubble_dname_' + UserPreferences().current.language + '_' + str(self.key())
        Cache().set(cache_key)

    @property
    def displaydate(self):
        if self.start_datetime and self.end_datetime:
            if self.start_datetime.strftime('%H:%M') == '00:00' and self.end_datetime.strftime('%H:%M') == '00:00':
                if self.start_datetime.strftime('%d.%m.%Y') == self.end_datetime.strftime('%d.%m.%Y'):
                    return self.start_datetime.strftime('%d.%m.%Y')
                else:
                    return self.start_datetime.strftime('%d.%m.%Y') + ' - ' + self.end_datetime.strftime('%d.%m.%Y')
            else:
                if self.start_datetime.strftime('%d.%m.%Y') == self.end_datetime.strftime('%d.%m.%Y'):
                    return self.start_datetime.strftime('%d.%m.%Y %H:%M') + ' - ' + self.end_datetime.strftime('%H:%M')
                else:
                    return self.start_datetime.strftime('%d.%m.%y %H:%M') + ' - ' + self.end_datetime.strftime('%d.%m.%y %H:%M')
        else:
            if self.start_datetime:
                return self.start_datetime.strftime('%d.%m.%Y %H:%M') + ' - ...'
            else:
                if self.end_datetime:
                    return '... - ' + self.end_datetime.strftime('%d.%m.%Y %H:%M')
                else:
                    return ''

    @property
    def subbubbles(self):
        return GetUniqueList(self.mandatory_bubbles + self.optional_bubbles)


    def GetPhotoUrl(self, size = ''):
        return 'http://www.gravatar.com/avatar/%s?s=%s&d=identicon' % (hashlib.md5(str(self.key()).strip().lower()).hexdigest(), size)

    def GetType(self):
        return db.Query(BubbleType).filter('type', self.type).get()

    def GetTypedTags(self):
        result = {}
        for tag in self.typed_tags:
            result[tag.split(':')[0]] = tag.split(':')[1]
        return result

    def GetSeeders(self):
        return Person().get(self.seeders)

    def GetLeechers(self):
        return Person().get(self.leechers)

    def GetNextInLines(self):
        return Bubble().get(self.next_in_line)

    def GetPrerequisiteBubbles(self):
        return Bubble.get(self.prerequisite_bubbles)

    def WaitinglistToLeecher(self):
        for bp in db.Query(BubblePerson).filter('bubble', self).filter('status', 'waiting').order('start_datetime'):
            if self.maximum_leecher_count:
                if self.maximum_leecher_count <= len(self.leechers):
                    break
            self.leechers = AddToList(bp.person.key(), self.leechers)
            self.put()

            person = bp.person
            person.leecher = AddToList(bp.bubble.key(), person.leecher)
            person.put()

            bp.end_datetime = datetime.now()
            bp.status = 'waiting_end'
            bp.put()

    @property
    def PrevInLines(self):
        return db.Query(Bubble).filter('next_in_line', self.key()).fetch(1000)

    @property
    def MandatoryInBubbles(self):
        return db.Query(Bubble).filter('mandatory_bubbles', self.key()).fetch(1000)

    @property
    def OptionalInBubbles(self):
        return db.Query(Bubble).filter('optional_bubbles', self.key()).fetch(1000)

    @property
    def InBubblesD(self):
        in_bubbles = {}
        for b in self.InBubbles:
            in_bubbles[b.key()] = b
        return in_bubbles

    @property
    def InBubbles(self):
        in_bubbles = self.in_bubbles
        if in_bubbles:
            return in_bubbles
        else:
            return []

    @property
    def in_bubbles(self):                       # TODO refactor to InBubbles
        return self.MandatoryInBubbles + self.OptionalInBubbles

    @property
    def PrerequisiteForBubbles(self):
        return db.Query(Bubble).filter('prerequisite_bubbles', self.key()).fetch(1000)

    @property
    def PrerequisiteBubbles(self):
        bubbles = []
        if self.prerequisite_bubbles:
            for b in Bubble.get(self.prerequisite_bubbles):
                if not b:
                    continue
                if b.is_deleted:
                    continue
                bubbles.append(b)
        return bubbles

    @property
    def SubBubblesD(self):
        sub_bubbles = {}
        for b in self.SubBubbles:
            sub_bubbles[b.key()] = b
        return sub_bubbles

    @property
    def SubBubbles(self):
        sub_bubbles = self.bubbles
        if sub_bubbles:
            return sub_bubbles
        else:
            return []

    @property
    def bubbles(self):                         # TODO refactor to SubBubbles
        keys = []
        if self.mandatory_bubbles:
            keys += self.mandatory_bubbles
        if self.optional_bubbles:
            keys += self.optional_bubbles
        keys = GetUniqueList(keys)
        if len(keys) == 0:
            return

        bubbles = []
        for b in Bubble.get(keys):
            if not b:
                continue
            if b.is_deleted:
                continue
            if b.key() in self.mandatory_bubbles:
                b.is_mandatory = True
            else:
                b.is_mandatory = False
            bubbles.append(b)
        if len(bubbles) > 0:
            return bubbles

    @property
    def RateableSubBubbles(self):
        keys = []
        if self.mandatory_bubbles:
            keys += self.mandatory_bubbles
        if self.optional_bubbles:
            keys += self.optional_bubbles
        keys = GetUniqueList(keys)
        if len(keys) == 0:
            return

        bubbles = []
        for b in Bubble.get(keys):
            if not b:
                continue
            if b.is_deleted:
                continue
            if b.rating_scale is None:
                continue
            if b.key() in self.mandatory_bubbles:
                b.is_mandatory = True
            else:
                b.is_mandatory = False
            bubbles.append(b)
        if len(bubbles) > 0:
            return bubbles

    @property
    def MandatoryBubbles(self):
        if self.mandatory_bubbles is None:
            return
        bubbles = []
        for b in Bubble.get(self.mandatory_bubbles):
            if not b:
                continue
            if b.is_deleted:
                continue
            b.is_mandatory = True
            bubbles.append(b)
        if len(bubbles) > 0:
            return bubbles

    @property
    def OptionalBubbles(self):
        if self.optional_bubbles:
            bubbles = []
            for b in Bubble.get(self.optional_bubbles):
                if not b:
                    continue
                if b.is_deleted:
                    continue
                b.is_mandatory = False
                bubbles.append(b)
            if len(bubbles) > 0:
                return bubbles

    @property
    def PersonGrades(self, person_key):
        return db.Query(Grade).filter('person', person_key).filter('bubble',self.key()).fetch(1000)

    # i.e. Pre-requisite bubbles must notify post-requisites when marked green so
    # that they can check, if they are next in line for at least one green bubble
    def propose_leecher(self, person_key):
        for bubble in self.PrevInLines:
            if bubble.is_green(person_key):
                return self.add_leecher(person_key)

        return False

    # Could we add person to bubble.leechers?
    def is_valid_leecher(self, person_key):
        if leecher in self.leechers:
            return False
        return self.are_prerequisites_satisfied(person_key)

    @property
    def Grades(self):
        return db.Query(Grade).filter('bubble', self.key()).filter('is_deleted', False).fetch(1000)

    @property
    def SubGrades(self):
        subgrades = []
        for bubble_key in self.sub_bubbles:
            subgrades.extend(db.Query(Grade).filter('bubble', bubble_key).filter('is_deleted', False).fetch(1000))
        return subgrades

    @property
    def is_started(self):
        return self.start_datetime < datetime.now()

    @property
    def is_finished(self):
        return self.end_datetime < datetime.now()

    @property
    def is_currently_on(self):
        return self.is_started() and not self.is_finished()

    def add_leecher(self, person_key):
        #if not self.is_valid_leecher(person_key):
        #    return False

        self.leechers = AddToList(person_key, self.leechers)
        self.put()

        if self.type == 'exam':
            person = Person().get(person_key)
            if not list(set(person.leecher) & set(self.optional_bubbles)):
                bubbles = sorted(Bubble().get(self.optional_bubbles), key=attrgetter('start_datetime'))
                for b in bubbles:
                    if b.type == 'personal_time_slot' and b.is_deleted == False:
                        if not db.Query(Person).filter('leecher', b.key()).get():
                            person.add_leecher(b.key())
                            break

        if self.type == 'personal_time_slot':
            person = Person().get(person_key)
            bubble = db.Query(Bubble).filter('type', 'exam').filter('optional_bubbles', self.key()).get()

            if bubble.description:
                description = bubble.description.value
            else:
                description = ''

            con = db.Query(Conversation).filter('entities', person.key()).filter('types', 'application').get()
            if not con:
                con = Conversation()
                con.types = ['application']
                con.entities = [person.key()]
            con.participants = AddToList(person.key(), con.participants)
            con.put()
            """con.add_message(
                message = Translate('email_log_timeslot') % {
                    'bubble': bubble.displayname,
                    'description': description,
                    'time': self.displaydate,
                    'link': bubble.url,
                }
            )

            SendMail(
                to = person.emails,
                reply_to = 'sisseastumine@artun.ee',
                subject = Translate('email_subject_timeslot') % bubble.displayname,
                message = Translate('email_message_timeslot') % {
                    'name': person.displayname,
                    'bubble': bubble.displayname,
                    'description': description,
                    'time': self.displaydate,
                    'link': bubble.url,
                }
            )"""

    def remove_leecher(self, person_key):
        self.leechers.remove(person_key)
        self.put()

    def remove_optional_bubble(self, bubble_key):
        self.optional_bubbles.remove(bubble_key)
        self.put()

    def get_subgrades_bubbles(self):
        grades_bubbles = []
        if self.bubbles:
            for b in self.bubbles:
                if b.type != 'personal_time_slot':
                    if b.type2.grade_display_method == 'all':
                        grades_bubbles = grades_bubbles + b.grades(person_key)
                    else:
                        grades_bubbles.append(b)
            grades_bubbles = sorted(grades_bubbles, key=lambda k: k.key())
        return grades_bubbles

    def subgrades(self, person_key):
        bubbles = self.get_subgrades_bubbles()
        for b in bubbles:
            b.grade = db.Query(Grade).filter('bubble', b.key()).filter('is_deleted', False).filter('person', person_key).get()

        return bubbles

    def has_positive_grade(self, person_key):
        grades = self.PersonGrades(person_key)
        if len(grades) == 0:
            return False

        for grade in sorted(grades, attrgetter('datetime', reverse=True)):
            if grade.is_positive:
                return True
            if self.type2.grade_display_method == 'latest':
                return False

        return False

    def mark_green(person_key):
        self.green_persons = AddToList(person_key, self.green_persons)
        self.put()
        for bubble in self.PrerequisiteForBubbles:
            bubble.propose_leecher(person_key)

    def is_green(person_key):
        if person_key in self.green_persons:
            return True

        if self.rating_scale:
            if not self.has_positive_grade(person_key):
                return False

        if not self.are_mandatories_satisfied(person_key):
            return False

        if self.minimum_bubble_count > 0:
            counter = self.minimum_bubble_count
            for sub_bubble in self.SubBubbles:
                if sub_bubble.is_green(person_key):
                    counter = counter - 1
                    if counter == 0:
                        return True
                return False

        self.mark_green(person_key)
        return True

    def recheck_green(person_key):
        RemoveFromList(person_key, self.green_persons)
        return self.is_green(person_key)

    def are_mandatories_satisfied(person_key):
        for sub_bubble in self.MandatoryBubbles:
            if not sub_bubble.is_green(person_key):
                return False
        return True

    def are_prerequisites_satisfied(person_key):
        for pre_bubble in self.PrerequisiteBubbles:
            if not pre_bubble.is_green(person_key):
                return False
        return True

    # Positive grades are only available, if mandatories are green.
    # Negative grades could be issued at any time.
    def grades_available(person_key):
        if not self.rating_scale:
            return

        if self.are_mandatories_satisfied(person_key):
            return self.rating_scale.GradeDefinitions

        return self.rating_scale.NegativeGradeDefinitions

    # When rating a bubble with rated sub-bubbles, sub-bubble grades could be listed.
    def sub_bubble_grades(person_key):
        for sub_bubble in self.SubBubbles:
            grades = grades + sub_bubble.PersonGrades(person_key)

        return grades


class BubblePerson(ChangeLogModel): #parent=Bubble()
    bubble          = db.ReferenceProperty(Bubble)
    person          = db.ReferenceProperty(Person)
    status          = db.StringProperty(choices=['waiting', 'waiting_end', 'leecher', 'seeder', 'canceled'])
    start_datetime  = db.DateTimeProperty(auto_now_add=True)
    end_datetime    = db.DateTimeProperty()


class GradeDefinition(ChangeLogModel):
    rating_scale    = db.ReferenceProperty(RatingScale)
    name            = db.ReferenceProperty(Dictionary, collection_name='gradedefinition_name')
    is_positive     = db.BooleanProperty()
    equivalent      = db.IntegerProperty()

    @property
    def displayname(self):
        return self.name.value


class Grade(ChangeLogModel):
    person          = db.ReferenceProperty(Person, collection_name='grades')
    gradedefinition = db.ReferenceProperty(GradeDefinition, collection_name='grades')
    bubble          = db.ReferenceProperty(Bubble)
    bubble_type     = db.StringProperty()
    subject_name    = db.ReferenceProperty(Dictionary, collection_name='grade_subject_name')
    datetime        = db.DateTimeProperty()
    name            = db.ReferenceProperty(Dictionary, collection_name='grade_name')
    equivalent      = db.IntegerProperty()
    is_positive     = db.BooleanProperty()
    points          = db.FloatProperty()
    school          = db.ReferenceProperty(Dictionary, collection_name='grade_school')
    teacher         = db.ReferenceProperty(Person, collection_name='given_grades')
    teacher_name    = db.StringProperty()
    typed_tags      = db.StringListProperty()
    is_locked       = db.BooleanProperty(default=False)

    @property
    def displayname(self):
        if self.name:
            return self.name.value
        else:
            if self.gradedefinition:
                if self.gradedefinition.name:
                    return self.gradedefinition.name.value
        return ''

    @property
    def displaydate(self):
        if self.datetime:
            return self.datetime.strftime('%d.%m.%Y %H:%M')
        else:
            return '...'
