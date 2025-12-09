from app.data.database import db_manager
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULTS = {
    'SpaceComponent': {
        'K_sed': '1e-5', 'K_br': '1e-7', 'F_f': '0.0', 'phi': '0.3', 'H_star': '0.1',
        'v_s': '0.001', 'm_sp': '0.5', 'n_sp': '1.0', 'sp_crit_sed': '0.0', 'sp_crit_br': '0.0',
        'discharge_field': 'surface_water__discharge', 'solver': 'basic'
    },
    'SpaceLargeScaleEroderComponent': {
        'K_sed': '1e-5', 'K_br': '1e-7', 'F_f': '0.0', 'phi': '0.3', 'H_star': '0.1',
        'v_s': '0.001', 'm_sp': '0.5', 'n_sp': '1.0', 'sp_crit_sed': '0.0', 'sp_crit_br': 0.0,
        'discharge_field': 'surface_water__discharge', 'thickness_lim': '100.0'
    },
    'FlowAccumulatorComponent': {
        'flow_director': 'D8', 'runoff_rate': '1.0'
    },
    'DepthDependentDiffuserComponent': {
        'linear_diffusivity': '0.01', 'soil_transport_decay_depth': '0.5'
    }
}

def verify_and_fix():
    session = db_manager.get_session()
    try:
        logger.info("Verifying defaults in DB...")
        for comp_name, params in DEFAULTS.items():
            comp_id_row = session.execute(text("SELECT id FROM component WHERE name = :name"), {'name': comp_name}).fetchone()
            if not comp_id_row:
                logger.error(f"Component {comp_name} MISSING from DB.")
                continue
            
            comp_id = comp_id_row[0]
            
            for param_key, default_val in params.items():
                p_result = session.execute(
                    text("SELECT default_value FROM component_param WHERE component_id = :cid AND key = :key"),
                    {'cid': comp_id, 'key': param_key}
                ).fetchone()
                
                if not p_result:
                    logger.warning(f"Param {param_key} missing for {comp_name}. Inserting...")
                    session.execute(
                        text("INSERT INTO component_param (component_id, key, type, default_value) VALUES (:cid, :key, 'QLineEdit', :val)"),
                        {'cid': comp_id, 'key': param_key, 'val': default_val}
                    )
                else:
                    current_val = p_result[0]
                    if current_val != default_val:
                        logger.warning(f"Param {param_key} for {comp_name} is '{current_val}'. Expected '{default_val}'. Updating...")
                        session.execute(
                            text("UPDATE component_param SET default_value = :val WHERE component_id = :cid AND key = :key"),
                            {'cid': comp_id, 'key': param_key, 'val': default_val}
                        )
                    else:
                        logger.info(f"Param {param_key} OK.")
        
        session.commit()
        logger.info("Verification/Fix complete.")
        
    except Exception as e:
        session.rollback()
        logger.error(f"Verification failed: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    verify_and_fix()
