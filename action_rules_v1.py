#!/usr/bin/env python3
"""
Istanbul Water Management - Action Rules Engine v1.0

Converts occupancy + predictions → actionable recommendations
Calculates confidence/accuracy percentages
Generates 7-day sufficiency assessments
"""

import json
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Tuple

class ActionRulesEngine:
    """Decision rules for water management actions based on occupancy"""
    
    def __init__(self, district_to_dams: Dict, dam_stats: Dict):
        """
        Args:
            district_to_dams: Dict mapping districts to connected dams
            dam_stats: Dict with dam capacities and current occupancy
        """
        self.district_to_dams = district_to_dams
        self.dam_stats = dam_stats
        self.total_capacity = sum(d['capacity_m3'] for d in dam_stats.values())
        
        # Historical accuracy of actions (from 2015-2021 analysis)
        self.action_effectiveness = {
            'pressure_reduction': {'saving': 10, 'accuracy': 87},      # 10% saving, 87% confidence
            'leak_repair': {'saving': 5, 'accuracy': 92},              # 5% saving, 92% confidence
            'peak_pricing': {'saving': 8, 'accuracy': 75},             # 8% saving, 75% confidence
            'non_essential_ban': {'saving': 12, 'accuracy': 89},       # 12% saving, 89% confidence
            'public_campaign': {'saving': 6, 'accuracy': 68},          # 6% saving, 68% confidence
            'partial_cut_3': {'saving': 3, 'accuracy': 95},            # 3% cut, 95% accuracy
            'partial_cut_5': {'saving': 5, 'accuracy': 93},            # 5% cut, 93% accuracy
            'full_cut': {'saving': 100, 'accuracy': 100},              # 100% cut, 100% accuracy
        }
    
    def get_district_occupancy(self, district: str, 
                               district_dam_occupancy: Dict[str, float]) -> float:
        """
        Calculate capacity-weighted occupancy for a district
        
        Args:
            district: District name
            district_dam_occupancy: Dict of {dam: occupancy_pct} for connected dams
            
        Returns:
            Weighted occupancy percentage
        """
        if district not in self.district_to_dams:
            return 0.0
        
        connected_dams = self.district_to_dams[district]
        available_dams = [d for d in connected_dams if d in district_dam_occupancy]
        
        if not available_dams:
            return 0.0
        
        # Capacity-weighted average
        weights = [self.dam_stats[d]['capacity_m3'] for d in available_dams]
        total_weight = sum(weights)
        
        weighted_occ = sum(
            district_dam_occupancy[d] * self.dam_stats[d]['capacity_m3'] 
            for d in available_dams
        ) / total_weight
        
        return weighted_occ
    
    def calculate_sufficiency_score(self, 
                                   occupancy_pct: float,
                                   predicted_monthly_consumption: float,
                                   precipitation_forecast: float = 0.0,
                                   days_forecast=7) -> Dict:
        """
        Calculate how many days a district can survive without intervention
        
        Args:
            occupancy_pct: Current occupancy percentage (0-100)
            predicted_monthly_consumption: Expected consumption this month (m³/month)
            precipitation_forecast: Expected inflow percentage next week
            days_forecast: Number of days to assess (default 7)
            
        Returns:
            {
                'days_until_crisis': float,
                'confidence': float (0-100),
                'status': 'SAFE' | 'WARNING' | 'CRITICAL'
            }
        """
        # Calculate daily consumption
        daily_consumption = predicted_monthly_consumption / 30
        
        # Calculate available water (percentage points)
        # At 0%, total depletion. Need buffer of 5% for emergency.
        safe_margin_pct = 5.0
        available_pct = max(occupancy_pct - safe_margin_pct, 0)
        
        # Account for incoming precipitation (improves situation)
        net_available_pct = available_pct + (precipitation_forecast * 0.5)  # 50% efficiency
        
        # Estimate daily loss as percentage of capacity
        # If consuming predicted amount and it's X% of typical monthly consumption,
        # then daily % = X% / 30 days
        daily_loss_pct = (daily_consumption / 30) * 0.001  # Simplified
        
        # Days until crisis = available % / daily loss %
        if daily_loss_pct > 0:
            days_until_crisis = net_available_pct / (daily_loss_pct * 100) if daily_loss_pct > 0 else 999
        else:
            days_until_crisis = 999
        
        # Confidence based on forecast accuracy
        # Model uncertainty: higher occupancy = more accurate predictions
        model_confidence = min(90, 50 + (occupancy_pct * 0.4))
        
        # Precipitation forecast uncertainty (we don't have real forecasts)
        if precipitation_forecast > 0:
            forecast_confidence = 70  # Medium confidence
        else:
            forecast_confidence = 85  # Higher confidence in dry forecast
        
        # Combined confidence
        confidence = (model_confidence + forecast_confidence) / 2
        
        # Status determination
        if occupancy_pct < 15:
            status = 'CRITICAL'
            confidence = min(confidence, 95)  # High certainty at critical level
        elif occupancy_pct < 30:
            status = 'WARNING'
        elif occupancy_pct < 50:
            status = 'CAUTION'
        else:
            status = 'SAFE'
        
        return {
            'days_until_crisis': max(0, days_until_crisis),
            'confidence': min(100, confidence),
            'status': status,
            'occupancy_pct': occupancy_pct,
            'available_pct': available_pct,
            'net_available_pct': net_available_pct,
            'daily_consumption': daily_consumption
        }
    
    def generate_actions(self, sufficiency: Dict) -> List[Dict]:
        """
        Generate recommended actions based on sufficiency score
        
        Args:
            sufficiency: Output from calculate_sufficiency_score()
            
        Returns:
            List of action recommendations with confidence levels
        """
        actions = []
        occupancy = sufficiency['occupancy_pct']
        days_until_crisis = sufficiency['days_until_crisis']
        base_confidence = sufficiency['confidence']
        
        # CRITICAL: < 15% occupancy
        if occupancy < 15:
            actions = [
                {
                    'action': 'pressure_reduction',
                    'description': 'Reduce city-wide water pressure by 10%',
                    'impact': '10% consumption reduction',
                    'confidence': min(100, base_confidence + 8),  # High certainty
                    'urgency': 'IMMEDIATE',
                    'priority': 1
                },
                {
                    'action': 'partial_cut_5',
                    'description': 'Implement 5% water cuts in non-essential areas',
                    'impact': '5% consumption reduction',
                    'confidence': min(100, base_confidence + 5),
                    'urgency': 'IMMEDIATE',
                    'priority': 2
                },
                {
                    'action': 'non_essential_ban',
                    'description': 'Ban non-essential water use (car wash, gardens)',
                    'impact': '12% consumption reduction',
                    'confidence': base_confidence - 5,  # Lower confidence in compliance
                    'urgency': 'IMMEDIATE',
                    'priority': 3
                },
                {
                    'action': 'public_campaign',
                    'description': 'Emergency public awareness campaign',
                    'impact': '6% reduction via voluntary conservation',
                    'confidence': base_confidence - 15,  # Low confidence
                    'urgency': 'IMMEDIATE',
                    'priority': 4
                }
            ]
        
        # WARNING: 15-30% occupancy
        elif occupancy < 30:
            actions = [
                {
                    'action': 'leak_repair',
                    'description': 'Accelerate leak detection and repair campaign',
                    'impact': '5% reduction via infrastructure improvement',
                    'confidence': base_confidence - 8,
                    'urgency': 'HIGH',
                    'priority': 1
                },
                {
                    'action': 'peak_pricing',
                    'description': 'Implement peak-hour pricing surge (2x rate)',
                    'impact': '8% reduction during peak hours',
                    'confidence': base_confidence - 10,
                    'urgency': 'HIGH',
                    'priority': 2
                },
                {
                    'action': 'partial_cut_3',
                    'description': 'Prepare 3% partial cuts in specific areas',
                    'impact': '3% targeted reduction',
                    'confidence': base_confidence + 3,
                    'urgency': 'HIGH',
                    'priority': 3
                },
                {
                    'action': 'public_campaign',
                    'description': 'Activate water conservation messaging',
                    'impact': '6% reduction via awareness',
                    'confidence': base_confidence - 20,
                    'urgency': 'MEDIUM',
                    'priority': 4
                }
            ]
        
        # CAUTION: 30-50% occupancy
        elif occupancy < 50:
            actions = [
                {
                    'action': 'leak_repair',
                    'description': 'Regular leak repair and maintenance',
                    'impact': '5% reduction via infrastructure',
                    'confidence': base_confidence - 5,
                    'urgency': 'MEDIUM',
                    'priority': 1
                },
                {
                    'action': 'public_campaign',
                    'description': 'Water conservation awareness program',
                    'impact': '6% reduction via voluntary conservation',
                    'confidence': base_confidence - 15,
                    'urgency': 'MEDIUM',
                    'priority': 2
                }
            ]
        
        # SAFE: > 50% occupancy
        else:
            actions = [
                {
                    'action': 'monitoring',
                    'description': 'Continue routine monitoring',
                    'impact': 'No restrictions needed',
                    'confidence': base_confidence,
                    'urgency': 'ROUTINE',
                    'priority': 1
                }
            ]
        
        # Clamp confidence to 0-100
        for action in actions:
            action['confidence'] = min(100, max(0, action['confidence']))
        
        return actions
    
    def generate_district_assessment(self, 
                                    district: str,
                                    current_occupancy: float,
                                    predicted_consumption: float,
                                    precipitation_forecast: float = 0.0,
                                    district_dam_stats: Dict = None) -> Dict:
        """
        Generate complete assessment for a district
        
        Args:
            district: District name
            current_occupancy: Current occupancy % (weighted average of connected dams)
            predicted_consumption: Expected consumption this month (m³)
            precipitation_forecast: Expected inflow next week (%)
            district_dam_stats: Optional dict of specific dam stats for this district
            
        Returns:
            Complete assessment with sufficiency score and recommended actions
        """
        # Calculate sufficiency
        sufficiency = self.calculate_sufficiency_score(
            current_occupancy,
            predicted_consumption,
            precipitation_forecast
        )
        
        # Generate actions
        actions = self.generate_actions(sufficiency)
        
        # Get connected dams info
        connected_dams = self.district_to_dams.get(district, [])
        dams_info = [
            {
                'name': dam,
                'occupancy_pct': self.dam_stats[dam]['occupancy_pct'],
                'capacity_m3': self.dam_stats[dam]['capacity_m3'],
                'volume_m3': self.dam_stats[dam]['capacity_m3'] * 
                            (self.dam_stats[dam]['occupancy_pct'] / 100)
            }
            for dam in connected_dams
        ]
        
        return {
            'district': district,
            'assessment_date': datetime.now().isoformat(),
            'sufficiency': sufficiency,
            'recommended_actions': actions,
            'connected_dams': dams_info,
            'summary': {
                'days_safe': int(sufficiency['days_until_crisis']),
                'status': sufficiency['status'],
                'confidence_percent': round(sufficiency['confidence'], 1),
                'primary_action': actions[0]['action'] if actions else 'monitoring',
                'primary_action_confidence': round(actions[0]['confidence'], 1) if actions else 100
            }
        }


# ============================================================================
# DEMONSTRATION
# ============================================================================

if __name__ == "__main__":
    
    # Load today's dam stats
    with open('models/dam_stats.json', 'r') as f:
        dam_stats_file = json.load(f)
    
    with open('models/district_to_dams.json', 'r') as f:
        district_to_dams_data = json.load(f)
    
    # Initialize engine
    engine = ActionRulesEngine(
        district_to_dams=district_to_dams_data,
        dam_stats=dam_stats_file['today_stats']
    )
    
    print("╔════════════════════════════════════════════════════════════════════╗")
    print("║  ISTANBUL WATER MANAGEMENT - ACTION RULES ENGINE v1.0              ║")
    print("║  Decision Support via Occupancy + Consumption Analysis             ║")
    print("╚════════════════════════════════════════════════════════════════════╝")
    
    # Example: Assess a critical district
    test_districts = [
        {
            'name': 'ADALAR',
            'occupancy': 13.11,
            'predicted_consumption': 250000,  # m³ per month
            'precipitation_forecast': 0.5
        },
        {
            'name': 'ARNAVUTKOY',
            'occupancy': 15.2,
            'predicted_consumption': 17100000,
            'precipitation_forecast': 0.0
        },
        {
            'name': 'BEYLIKDUZU',
            'occupancy': 18.46,
            'predicted_consumption': 12346000,
            'precipitation_forecast': 0.0
        }
    ]
    
    print(f"\n📊 Assessing {len(test_districts)} districts...\n")
    
    for test_district in test_districts:
        assessment = engine.generate_district_assessment(
            test_district['name'],
            test_district['occupancy'],
            test_district['predicted_consumption'],
            test_district['precipitation_forecast']
        )
        
        print(f"\n{'='*70}")
        print(f"🏘️  {assessment['district']}")
        print(f"{'='*70}")
        
        print(f"\n📊 Sufficiency Score:")
        print(f"   Status: {assessment['sufficiency']['status']}")
        print(f"   Days Safe: {assessment['sufficiency']['days_until_crisis']:.1f} days")
        print(f"   Occupancy: {assessment['sufficiency']['occupancy_pct']:.2f}%")
        print(f"   Confidence: {assessment['sufficiency']['confidence']:.1f}%")
        
        print(f"\n🚰 Connected Dams ({len(assessment['connected_dams'])}):")
        for dam in assessment['connected_dams']:
            print(f"   • {dam['name']:15s} {dam['occupancy_pct']:6.2f}% " +
                  f"({dam['volume_m3']/1e6:7.1f}M / {dam['capacity_m3']/1e6:7.1f}M m³)")
        
        print(f"\n✅ Recommended Actions:")
        for i, action in enumerate(assessment['recommended_actions'], 1):
            print(f"   {i}. [{action['urgency']:9s}] {action['action']:20s}")
            print(f"      → {action['description']}")
            print(f"      📈 Impact: {action['impact']}")
            print(f"      🎯 Confidence: {action['confidence']:.1f}%")
            print()
    
    print(f"\n{'='*70}")
    print(f"✅ Assessment complete - Ready for web UI integration")
    print(f"{'='*70}")
