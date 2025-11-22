"""
LawyerHub Reward System Algorithm
---------------------------------
This module contains the core logic for the LawyerHub reward system, including:
- Calculating reward points based on lawyer performance
- Determining reward tiers and eligibility
- Awarding badges based on performance metrics
- Calculating visibility boosts in search results
"""

from datetime import datetime, timedelta
import math


class RewardSystem:
    """Main class for handling the LawyerHub reward system"""
    
    # Constants for reward tiers
    TIER_THRESHOLDS = {
        'standard': 0,
        'silver': 150,
        'gold': 300,
        'platinum': 500
    }
    
    # Rating thresholds for tiers
    TIER_RATING_REQUIREMENTS = {
        'standard': 0,
        'silver': 3.5,
        'gold': 4.0,
        'platinum': 4.5
    }
    
    # Review count thresholds for tiers
    TIER_REVIEW_REQUIREMENTS = {
        'standard': 0,
        'silver': 10,
        'gold': 20,
        'platinum': 30
    }
    
    # Badge criteria
    BADGE_CRITERIA = {
        'Top Rated': {'min_rating': 4.8, 'min_reviews': 10},
        'Client Favorite': {'min_rating': 4.5, 'min_reviews': 20},
        'Rising Star': {'min_rating': 4.0, 'min_reviews': 5, 'max_reviews': 15, 'max_days_registered': 180},
        'Experienced Pro': {'min_reviews': 30},
        'Perfect Score': {'exact_rating': 5.0, 'min_reviews': 3},
        'Quick Responder': {'response_rate': 0.9, 'avg_response_time_hours': 4, 'min_inquiries': 15},
        'Case Winner': {'success_rate': 0.75, 'min_cases': 10},
        'Top 10%': {'percentile': 10, 'metric': 'rating', 'min_reviews': 15}
    }
    
    # Points calculation weights
    WEIGHTS = {
        'rating': 100,        # Base points for a 5.0 rating
        'review': 10,         # Points per review
        'consultation': 5,    # Points per completed consultation
        'response_time': 50,  # Max points for response time (decreases as time increases)
        'success_rate': 100,  # Max points for 100% success rate
        'profile_quality': 50 # Max points for complete profile with all fields
    }
    
    def __init__(self, db_connection=None):
        """Initialize the reward system with optional database connection"""
        self.db = db_connection
    
    def calculate_reward_points(self, lawyer_data):
        """
        Calculate reward points based on lawyer performance metrics
        
        Parameters:
        -----------
        lawyer_data : dict
            Dictionary containing lawyer performance data including:
            - rating: float (1-5 scale)
            - review_count: int
            - consultations_completed: int
            - avg_response_time_minutes: float
            - success_rate: float (0-1)
            - profile_completion: float (0-1)
            - days_active: int
            
        Returns:
        --------
        int : Total reward points
        """
        points = 0
        
        # Points from rating (weighted by review count)
        if lawyer_data.get('rating') and lawyer_data.get('review_count'):
            rating = lawyer_data['rating']
            review_count = lawyer_data['review_count']
            rating_factor = rating / 5.0  # normalize to 0-1 scale
            review_weight = min(1.0, math.log10(review_count + 1) / 2)  # logarithmic scaling
            points += self.WEIGHTS['rating'] * rating_factor * review_weight
        
        # Points from reviews
        if lawyer_data.get('review_count'):
            points += lawyer_data['review_count'] * self.WEIGHTS['review']
        
        # Points from consultations
        if lawyer_data.get('consultations_completed'):
            points += lawyer_data['consultations_completed'] * self.WEIGHTS['consultation']
        
        # Points from response time (faster = more points)
        if lawyer_data.get('avg_response_time_minutes') is not None:
            # Convert to hours for calculation
            response_time_hours = lawyer_data['avg_response_time_minutes'] / 60
            
            # Use diminishing returns formula - faster responses get more points
            if response_time_hours <= 24:  # Cap at 24 hours
                response_factor = max(0, 1 - (response_time_hours / 24))
                points += self.WEIGHTS['response_time'] * response_factor
        
        # Points from success rate
        if lawyer_data.get('success_rate') is not None:
            points += self.WEIGHTS['success_rate'] * lawyer_data['success_rate']
        
        # Points from profile quality/completeness
        if lawyer_data.get('profile_completion') is not None:
            points += self.WEIGHTS['profile_quality'] * lawyer_data['profile_completion']
        
        # Apply activity bonus (more points for consistently active lawyers)
        if lawyer_data.get('days_active'):
            # Bonus caps at 2 years (730 days)
            activity_bonus = min(1.0, lawyer_data['days_active'] / 730)
            points *= (1 + (activity_bonus * 0.2))  # Up to 20% bonus
            
        return int(points)
    
    def determine_reward_tier(self, points, rating, review_count):
        """
        Determine lawyer's reward tier based on points, rating, and review count
        
        Parameters:
        -----------
        points : int
            Total reward points
        rating : float
            Average rating (1-5 scale)
        review_count : int
            Number of reviews
            
        Returns:
        --------
        str : Reward tier (standard, silver, gold, platinum)
        """
        # Start from the highest tier and work down
        for tier in ['platinum', 'gold', 'silver', 'standard']:
            points_requirement = self.TIER_THRESHOLDS[tier]
            rating_requirement = self.TIER_RATING_REQUIREMENTS[tier]
            review_requirement = self.TIER_REVIEW_REQUIREMENTS[tier]
            
            if (points >= points_requirement and 
                rating >= rating_requirement and 
                review_count >= review_requirement):
                return tier
                
        # Fallback to standard tier
        return 'standard'
    
    def check_badge_eligibility(self, lawyer_data):
        """
        Check which badges a lawyer is eligible for based on performance
        
        Parameters:
        -----------
        lawyer_data : dict
            Dictionary containing lawyer performance metrics
            
        Returns:
        --------
        list : List of badge names the lawyer is eligible for
        """
        eligible_badges = []
        
        for badge_name, criteria in self.BADGE_CRITERIA.items():
            # Check each criterion for the badge
            criteria_met = True
            
            # Check minimum rating
            if 'min_rating' in criteria:
                if lawyer_data.get('rating', 0) < criteria['min_rating']:
                    criteria_met = False
                    
            # Check exact rating
            if 'exact_rating' in criteria:
                if lawyer_data.get('rating', 0) != criteria['exact_rating']:
                    criteria_met = False
            
            # Check minimum reviews
            if 'min_reviews' in criteria:
                if lawyer_data.get('review_count', 0) < criteria['min_reviews']:
                    criteria_met = False
            
            # Check maximum reviews
            if 'max_reviews' in criteria:
                if lawyer_data.get('review_count', 0) > criteria['max_reviews']:
                    criteria_met = False
            
            # Check days registered limit
            if 'max_days_registered' in criteria:
                if lawyer_data.get('days_active', float('inf')) > criteria['max_days_registered']:
                    criteria_met = False
            
            # Check response rate
            if 'response_rate' in criteria:
                if lawyer_data.get('response_rate', 0) < criteria['response_rate']:
                    criteria_met = False
            
            # Check average response time
            if 'avg_response_time_hours' in criteria:
                avg_response_minutes = lawyer_data.get('avg_response_time_minutes', float('inf'))
                avg_response_hours = avg_response_minutes / 60
                if avg_response_hours > criteria['avg_response_time_hours']:
                    criteria_met = False
            
            # Check minimum inquiries
            if 'min_inquiries' in criteria:
                if lawyer_data.get('total_inquiries', 0) < criteria['min_inquiries']:
                    criteria_met = False
            
            # Check success rate
            if 'success_rate' in criteria:
                if lawyer_data.get('success_rate', 0) < criteria['success_rate']:
                    criteria_met = False
            
            # Check minimum cases
            if 'min_cases' in criteria:
                if lawyer_data.get('cases_completed', 0) < criteria['min_cases']:
                    criteria_met = False
            
            # Check percentile (requires database connection)
            if 'percentile' in criteria and self.db is not None:
                # This would need to be implemented with actual DB queries
                # For now, we'll assume this lawyer is in the top percentile
                pass
                
            # If all criteria are met, add badge to eligible list
            if criteria_met:
                eligible_badges.append(badge_name)
                
        return eligible_badges
    
    def calculate_search_boost(self, lawyer_tier, badges, recency_factor=1.0):
        """
        Calculate search result visibility boost based on reward tier and badges
        
        Parameters:
        -----------
        lawyer_tier : str
            Reward tier (standard, silver, gold, platinum)
        badges : list
            List of badge names the lawyer has earned
        recency_factor : float
            Factor to account for recent activity (1.0 = very active)
            
        Returns:
        --------
        float : Search boost factor (1.0 = no boost, higher values = better visibility)
        """
        # Base boost from tier
        tier_boosts = {
            'standard': 1.0,
            'silver': 1.2,
            'gold': 1.5,
            'platinum': 2.0
        }
        
        base_boost = tier_boosts.get(lawyer_tier, 1.0)
        
        # Additional boost from badges (up to 50% extra)
        badge_boost = min(0.5, len(badges) * 0.1)
        
        # Premium badges give extra boost
        premium_badges = ['Top Rated', 'Client Favorite', 'Perfect Score']
        premium_count = sum(1 for badge in badges if badge in premium_badges)
        premium_boost = premium_count * 0.1
        
        # Combine all factors and apply recency
        total_boost = (base_boost + badge_boost + premium_boost) * recency_factor
        
        return round(total_boost, 2)
    
    def process_lawyer_rewards(self, lawyer_id, lawyer_data):
        """
        Process all reward calculations for a lawyer and return updated data
        
        Parameters:
        -----------
        lawyer_id : str
            Unique identifier for the lawyer
        lawyer_data : dict
            Dictionary containing all lawyer metrics
            
        Returns:
        --------
        dict : Updated lawyer data with reward information
        """
        # Calculate reward points
        points = self.calculate_reward_points(lawyer_data)
        
        # Determine reward tier
        tier = self.determine_reward_tier(
            points, 
            lawyer_data.get('rating', 0),
            lawyer_data.get('review_count', 0)
        )
        
        # Check badge eligibility
        eligible_badges = self.check_badge_eligibility(lawyer_data)
        
        # Calculate search boost
        search_boost = self.calculate_search_boost(
            tier,
            eligible_badges,
            lawyer_data.get('recency_factor', 1.0)
        )
        
        # Prepare updated data
        reward_data = {
            'reward_points': points,
            'reward_tier': tier,
            'badges': eligible_badges,
            'search_boost': search_boost,
            'last_updated': datetime.utcnow()
        }
        
        # If database connection exists, update lawyer record
        if self.db is not None:
            # Check for tier change to record in history
            current_tier = lawyer_data.get('reward_tier', 'standard')
            if tier != current_tier:
                self._record_tier_change(lawyer_id, current_tier, tier, points)
                
            # Check for new badges
            current_badges = lawyer_data.get('badges', [])
            new_badges = [badge for badge in eligible_badges if badge not in current_badges]
            for badge in new_badges:
                self._record_badge_earned(lawyer_id, badge)
                
            # Update lawyer record in database
            self._update_lawyer_rewards(lawyer_id, reward_data)
            
        return reward_data
    
    def _record_tier_change(self, lawyer_id, old_tier, new_tier, points):
        """Record a tier change in the reward history (DB operation)"""
        if self.db is None:
            return
            
        history_entry = {
            'lawyer_id': lawyer_id,
            'event_type': 'tier_change',
            'description': f'Promoted from {old_tier} to {new_tier} tier',
            'previous_tier': old_tier,
            'new_tier': new_tier,
            'points': points,
            'created_at': datetime.utcnow()
        }
        
        # This would be implemented with actual DB operations
        # self.db.reward_history.insert_one(history_entry)
    
    def _record_badge_earned(self, lawyer_id, badge):
        """Record a new badge achievement in the reward history (DB operation)"""
        if self.db is None:
            return
            
        history_entry = {
            'lawyer_id': lawyer_id,
            'event_type': 'badge_earned',
            'description': f'Earned the "{badge}" badge',
            'badge_earned': badge,
            'created_at': datetime.utcnow()
        }
        
        # This would be implemented with actual DB operations
        # self.db.reward_history.insert_one(history_entry)
    
    def _update_lawyer_rewards(self, lawyer_id, reward_data):
        """Update lawyer record with new reward data (DB operation)"""
        if self.db is None:
            return
            
        # This would be implemented with actual DB operations
        # self.db.users.update_one(
        #     {'_id': lawyer_id},
        #     {'$set': reward_data}
        # )


def run_reward_system_update(db_connection):
    """
    Periodic job to update all lawyer rewards in the system
    
    Parameters:
    -----------
    db_connection : Database connection object
    """
    reward_system = RewardSystem(db_connection)
    
    # Get all lawyers from database
    # In a real implementation, this might be batched for large user bases
    lawyers_cursor = db_connection.users.find({'role': 'lawyer'})
    
    updated_count = 0
    for lawyer in lawyers_cursor:
        lawyer_id = str(lawyer['_id'])
        
        # Gather all metrics needed for reward calculation
        lawyer_metrics = {
            'rating': lawyer.get('rating', 0),
            'review_count': lawyer.get('review_count', 0),
            'consultations_completed': lawyer.get('consultations_completed', 0),
            'avg_response_time_minutes': _calculate_avg_response_time(db_connection, lawyer_id),
            'success_rate': _calculate_success_rate(db_connection, lawyer_id),
            'profile_completion': _calculate_profile_completion(lawyer),
            'days_active': _calculate_days_active(lawyer),
            'response_rate': _calculate_response_rate(db_connection, lawyer_id),
            'total_inquiries': _get_total_inquiries(db_connection, lawyer_id),
            'cases_completed': _get_completed_cases(db_connection, lawyer_id),
            'recency_factor': _calculate_recency_factor(lawyer),
            'reward_tier': lawyer.get('reward_tier', 'standard'),
            'badges': lawyer.get('badges', [])
        }
        
        # Process rewards for this lawyer
        reward_system.process_lawyer_rewards(lawyer_id, lawyer_metrics)
        updated_count += 1
    
    return {
        'updated_count': updated_count,
        'timestamp': datetime.utcnow()
    }


# Helper functions for gathering lawyer metrics
def _calculate_avg_response_time(db, lawyer_id):
    """Calculate average response time to client inquiries in minutes"""
    # This would query message history and calculate average response times
    # For this example, we'll return a random value
    import random
    return random.randint(10, 480)  # 10 minutes to 8 hours

def _calculate_success_rate(db, lawyer_id):
    """Calculate success rate based on case outcomes"""
    # This would query case history and calculate success percentage
    # For this example, we'll return a random value
    import random
    return random.uniform(0.6, 0.95)

def _calculate_profile_completion(lawyer_data):
    """Calculate profile completion percentage"""
    # List of fields that constitute a complete profile
    required_fields = [
        'name', 'specialty', 'location', 'bio', 'education',
        'experience', 'license_info', 'profile_image', 'contact_info'
    ]
    
    # Count how many fields are populated
    completed = sum(1 for field in required_fields if field in lawyer_data and lawyer_data[field])
    return completed / len(required_fields)

def _calculate_days_active(lawyer_data):
    """Calculate how many days the lawyer has been active on the platform"""
    if 'created_at' not in lawyer_data:
        return 0
        
    created_date = lawyer_data['created_at']
    days_active = (datetime.utcnow() - created_date).days
    return max(0, days_active)

def _calculate_response_rate(db, lawyer_id):
    """Calculate percentage of inquiries responded to within 24 hours"""
    # This would query message history
    # For this example, we'll return a random value
    import random
    return random.uniform(0.7, 0.98)

def _get_total_inquiries(db, lawyer_id):
    """Get total number of client inquiries received"""
    # This would query message/inquiry history
    # For this example, we'll return a random value
    import random
    return random.randint(10, 200)

def _get_completed_cases(db, lawyer_id):
    """Get number of completed cases"""
    # This would query case history
    # For this example, we'll return a random value
    import random
    return random.randint(5, 100)

def _calculate_recency_factor(lawyer_data):
    """
    Calculate recency factor based on recent activity
    Returns a value between 0.5 (inactive) and 1.2 (very active)
    """
    # This would analyze recent logins, messages, etc.
    # For this example, we'll return a random value
    import random
    return random.uniform(0.5, 1.2)


if __name__ == "__main__":
    # Example usage
    lawyer_data = {
        'rating': 4.8,
        'review_count': 42,
        'consultations_completed': 38,
        'avg_response_time_minutes': 45,
        'success_rate': 0.87,
        'profile_completion': 0.95,
        'days_active': 365,
        'response_rate': 0.93,
        'total_inquiries': 76,
        'cases_completed': 32,
        'recency_factor': 1.1
    }
    
    reward_system = RewardSystem()
    points = reward_system.calculate_reward_points(lawyer_data)
    tier = reward_system.determine_reward_tier(points, lawyer_data['rating'], lawyer_data['review_count'])
    badges = reward_system.check_badge_eligibility(lawyer_data)
    
    print(f"Lawyer earned {points} reward points")
    print(f"Reward tier: {tier}")
    print(f"Earned badges: {', '.join(badges)}")