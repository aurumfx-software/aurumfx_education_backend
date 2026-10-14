from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import Branch, BranchSidebarNavigation, User
from routers.auth import get_current_super_admin, get_current_user
from schemas.sidebar_navigation import SidebarNavigationUpdate


router = APIRouter(tags=["Sidebar Navigation"])

NAV_LINKS = {
    "dashboard": {"label": "Dashboard", "section": "Workspace"},
    "courses": {"label": "Courses", "section": "Workspace"},
    "staff": {"label": "Staff", "section": "Workspace"},
    "staff_verification": {"label": "Staff verification", "section": "Workspace"},
    "my_attendance": {"label": "My attendance", "section": "Workspace"},
    "register_student": {"label": "Register student", "section": "Students"},
    "view_students": {"label": "View students", "section": "Students"},
    "course_enrolments": {"label": "Course enrolments", "section": "Students"},
    "course_approvals": {"label": "Course approvals", "section": "Students"},
    "fees_due_students": {"label": "Fees due students", "section": "Students"},
    "student_fees": {"label": "Student fees", "section": "Students"},
    "enquiries": {"label": "Enquiries", "section": "Students"},
    "announcements": {"label": "Announcements", "section": "Business"},
    "messages": {"label": "Messages", "section": "Business"},
}
DEFAULT_NAV_LINKS = {key: True for key in NAV_LINKS}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_branch_navigation(db: Session, branch_id: int) -> dict[str, bool]:
    settings = (
        db.query(BranchSidebarNavigation)
        .filter(BranchSidebarNavigation.branch_id == branch_id)
        .first()
    )
    return {
        **DEFAULT_NAV_LINKS,
        **(settings.nav_links if settings else {}),
    }


def build_navigation_response(branch_id: int, nav_links: dict[str, bool]):
    return {
        "branch_id": branch_id,
        "nav_links": [
            {
                "key": key,
                **details,
                "visible": nav_links[key],
            }
            for key, details in NAV_LINKS.items()
        ],
    }


def get_branch(db: Session, branch_id: int) -> Branch:
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
    return branch


@router.get("/super-admin/branches/{branch_id}/sidebar-navigation")
def get_branch_sidebar_navigation(
    branch_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    get_branch(db, branch_id)
    return build_navigation_response(
        branch_id,
        get_branch_navigation(db, branch_id),
    )


@router.put("/super-admin/branches/{branch_id}/sidebar-navigation")
def update_branch_sidebar_navigation(
    branch_id: int,
    navigation_data: SidebarNavigationUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    get_branch(db, branch_id)
    supplied_keys = set(navigation_data.nav_links)
    required_keys = set(NAV_LINKS)
    if supplied_keys != required_keys:
        missing = sorted(required_keys - supplied_keys)
        unknown = sorted(supplied_keys - required_keys)
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Provide a true/false value for every sidebar link",
                "missing_nav_links": missing,
                "unknown_nav_links": unknown,
            },
        )

    settings = (
        db.query(BranchSidebarNavigation)
        .filter(BranchSidebarNavigation.branch_id == branch_id)
        .first()
    )
    if settings:
        settings.nav_links = navigation_data.nav_links
    else:
        settings = BranchSidebarNavigation(
            branch_id=branch_id,
            nav_links=navigation_data.nav_links,
        )
        db.add(settings)

    db.commit()
    db.refresh(settings)
    return build_navigation_response(branch_id, settings.nav_links)


@router.get("/branch-admin/sidebar-navigation")
def get_my_branch_sidebar_navigation(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "branch_admin":
        raise HTTPException(status_code=403, detail="Branch admin access required")
    if current_user.status != "Active":
        raise HTTPException(status_code=403, detail="Branch admin account is inactive")
    if not current_user.branch_id:
        raise HTTPException(
            status_code=400,
            detail="Branch admin is not assigned to a branch",
        )
    return build_navigation_response(
        current_user.branch_id,
        get_branch_navigation(db, current_user.branch_id),
    )
